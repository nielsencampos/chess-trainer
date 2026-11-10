"""Resolve and download the official Stockfish binary. Stdlib only.

  fetch_stockfish.py resolve VERSION OUT_FILE       write the release tag ("latest" -> newest)
  fetch_stockfish.py download TAG TARGET OUT_DIR    download, verify and extract the binary
  fetch_stockfish.py desktop [VERSION] [OUT_DIR]    this system's binary into .cache/

The image uses two steps so the Dockerfile can cache the 80 MB download by resolved tag. The
desktop build (desktop/chess-trainer.spec) uses `desktop`, which picks the target of the system
it runs on. TARGET is `amd64` or `arm64` (Linux, the image's TARGETARCH) or one of
`linux-amd64`, `linux-arm64`, `windows-amd64` and `macos` (one universal binary for Apple Silicon
and Intel).
"""

import hashlib
import json
import os
import platform
import re
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import NoReturn

REPO = "official-stockfish/Stockfish"
# Target -> (asset name without extension, archive extension, binary name in the archive).
TARGETS = {
    "linux-amd64": ("stockfish-linux-x86-64-universal", ".tar.gz", ""),
    "linux-arm64": ("stockfish-linux-arm64-universal", ".tar.gz", ""),
    "windows-amd64": ("stockfish-windows-x86-64-universal", ".zip", ".exe"),
    "macos": ("stockfish-macos-universal", ".tar.gz", ""),
}
TARGETS["amd64"] = TARGETS["linux-amd64"]  # the image's TARGETARCH
TARGETS["arm64"] = TARGETS["linux-arm64"]
FIRST_SUPPORTED = "sf_19"
TOKEN_FILE = Path("/run/secrets/github_token")
KEEP_DOCS = ("Copying.txt", "AUTHORS")
DESKTOP_DIR = Path(__file__).resolve().parent.parent / ".cache"


def fail(message: str) -> NoReturn:
    """Stops the build with a message.

    Args:
        message (str): What went wrong.
    """
    sys.exit(f"fetch_stockfish: {message}")


def resolve(version: str, out_file: Path) -> None:
    """Writes the release tag to build: the newest release for `latest`, else the tag given.

    Args:
        version (str): `latest` or a tag such as `sf_19`.
        out_file (Path): Where to write the tag.
    """
    if version == "latest":
        # The redirect, not the API: no rate limit, and it never points at a prerelease.
        with urllib.request.urlopen(
            f"https://github.com/{REPO}/releases/latest", timeout=30
        ) as response:
            tag = response.url.rstrip("/").rsplit("/", 1)[-1]
    else:
        tag = version
    if not re.fullmatch(r"[A-Za-z0-9._-]+", tag):
        fail(f"invalid release tag {tag!r}")
    out_file.write_text(f"{tag}\n", encoding="utf-8")
    print(f"resolved {version} -> {tag}")


def _release(tag: str) -> dict:
    """Reads a release from the GitHub API, with a token if the build has one.

    Args:
        tag (str): The release tag.

    Returns:
        dict: The release, with its assets.
    """
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "chess-trainer-build"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/tags/{tag}", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            fail(f"release {tag!r} does not exist")
        if error.code in (403, 429):
            fail(
                "GitHub API rate limit reached. Wait an hour, or build with "
                "--secret id=github_token,env=GITHUB_TOKEN"
            )
        raise


def _extract(archive: Path, wanted: dict[str, str], out_dir: Path) -> None:
    """Copies some files out of a release archive, a `.tar.gz` or a `.zip`.

    Args:
        archive (Path): The downloaded archive.
        wanted (dict[str, str]): Member name in the archive -> file name in `out_dir`.
        out_dir (Path): Where to write the files.
    """
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zipped:
            names = set(zipped.namelist())
            for member_name, target in wanted.items():
                if member_name not in names:
                    fail(f"{member_name} is not a file in {archive.name}")
                (out_dir / target).write_bytes(zipped.read(member_name))
        return
    with tarfile.open(archive) as tar:
        for member_name, target in wanted.items():
            source = tar.extractfile(member_name)
            if source is None:
                fail(f"{member_name} is not a file in {archive.name}")
            (out_dir / target).write_bytes(source.read())


def _fetch(url: str, path: Path, attempts: int = 4) -> "hashlib._Hash":
    """Downloads a file, retrying a server error or a dropped connection a few times.

    Args:
        url (str): The file's URL.
        path (Path): Where to write it.
        attempts (int): How many times to try.

    Returns:
        hashlib._Hash: The SHA-256 of what was written.
    """
    for attempt in range(1, attempts + 1):
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(url, timeout=300) as response, path.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    out.write(chunk)
            return digest
        except (urllib.error.URLError, OSError) as error:
            client_error = isinstance(error, urllib.error.HTTPError) and error.code < 500
            if client_error or attempt == attempts:
                raise
            print(f"download failed ({error}), retrying ({attempt}/{attempts - 1})")
            time.sleep(5 * attempt)
    raise AssertionError("unreachable")


def download(tag: str, target: str, out_dir: Path) -> None:
    """Downloads the universal binary of a release, verifies its digest and extracts it.

    Also keeps the license files and writes a `VERSION` file with the tag. The binary is named
    `stockfish`, or `stockfish.exe` on Windows.

    Args:
        tag (str): The release tag.
        target (str): A key of `TARGETS`, such as `amd64` or `windows-amd64`.
        out_dir (Path): Where to install it.
    """
    if target not in TARGETS:
        fail(f"unsupported target {target!r}; supported: {sorted(TARGETS)}")
    binary_name, extension, exe = TARGETS[target]
    asset_name = f"{binary_name}{extension}"
    assets = {asset["name"]: asset for asset in _release(tag)["assets"]}
    asset = assets.get(asset_name)
    if asset is None:
        fail(
            f"release {tag} has no {asset_name}. Only {FIRST_SUPPORTED} or newer is supported: "
            "older releases have no universal binary and no Linux arm64 build."
        )
    expected = asset.get("digest")
    if not expected:
        fail(f"release {tag} publishes no digest for {asset_name}")

    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        archive = Path(temp_dir) / asset_name
        digest = _fetch(asset["browser_download_url"], archive)
        if expected != f"sha256:{digest.hexdigest()}":
            fail(f"checksum mismatch for {asset_name}: expected {expected}")
        wanted = {f"stockfish/{binary_name}{exe}": f"stockfish{exe}"} | {
            f"stockfish/{doc}": doc for doc in KEEP_DOCS
        }
        _extract(archive, wanted, out_dir)
    os.chmod(out_dir / f"stockfish{exe}", 0o755)
    (out_dir / "VERSION").write_text(f"{tag}\n", encoding="utf-8")
    print(f"installed {asset_name} ({tag}), {expected}")


def host_target() -> str:
    """Names the target of the system this script runs on.

    Returns:
        str: A key of `TARGETS`.
    """
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32" and arch == "amd64":
        return "windows-amd64"
    if sys.platform == "linux" and arch:
        return f"linux-{arch}"
    fail(f"no Stockfish build for {sys.platform} on {machine}")


def desktop(version: str = "latest", out_dir: Path = DESKTOP_DIR) -> None:
    """Puts this system's Stockfish, its `VERSION` and licenses where the desktop build looks.

    Args:
        version (str): `latest` or a tag such as `sf_19`.
        out_dir (Path): Where to install it; the repo's `.cache/` by default.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tag_file = out_dir / "VERSION"
    resolve(version, tag_file)
    download(tag_file.read_text(encoding="utf-8").strip(), host_target(), out_dir)


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["resolve", version, out_file]:
            resolve(version, Path(out_file))
        case ["download", tag, target, out_dir]:
            download(tag, target, Path(out_dir))
        case ["desktop"]:
            desktop()
        case ["desktop", version]:
            desktop(version)
        case ["desktop", version, out_dir]:
            desktop(version, Path(out_dir))
        case _:
            fail(f"bad arguments: {sys.argv[1:]}")
