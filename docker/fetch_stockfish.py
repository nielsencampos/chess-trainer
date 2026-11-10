"""Resolve and download the official Stockfish binary at image build time. Stdlib only.

  fetch_stockfish.py resolve VERSION OUT_FILE       write the release tag ("latest" -> newest)
  fetch_stockfish.py download TAG ARCH OUT_DIR      download, verify and extract the binary

Two steps so the Dockerfile can cache the 80 MB download by resolved tag.
"""

import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = "official-stockfish/Stockfish"
ARCH_TO_ASSET = {"amd64": "linux-x86-64", "arm64": "linux-arm64"}
FIRST_SUPPORTED = "sf_19"
TOKEN_FILE = Path("/run/secrets/github_token")
KEEP_DOCS = ("Copying.txt", "AUTHORS")


def fail(message: str) -> None:
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
    if TOKEN_FILE.exists():
        headers["Authorization"] = f"Bearer {TOKEN_FILE.read_text(encoding='utf-8').strip()}"
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


def download(tag: str, arch: str, out_dir: Path) -> None:
    """Downloads the universal binary of a release, verifies its digest and extracts it.

    Also keeps the license files and writes a `VERSION` file with the tag.

    Args:
        tag (str): The release tag.
        arch (str): `amd64` or `arm64`.
        out_dir (Path): Where to install it.
    """
    if arch not in ARCH_TO_ASSET:
        fail(f"unsupported architecture {arch!r}; supported: {sorted(ARCH_TO_ASSET)}")
    binary_name = f"stockfish-{ARCH_TO_ASSET[arch]}-universal"
    asset_name = f"{binary_name}.tar.gz"
    assets = {asset["name"]: asset for asset in _release(tag)["assets"]}
    asset = assets.get(asset_name)
    if asset is None:
        fail(
            f"release {tag} has no {asset_name}. Only {FIRST_SUPPORTED} or newer is supported: "
            "older releases have no universal binary and no Linux arm64 build."
        )

    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as archive:
        with urllib.request.urlopen(asset["browser_download_url"], timeout=300) as response:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                archive.write(chunk)
        archive.flush()
        expected = asset.get("digest")
        if not expected:
            fail(f"release {tag} publishes no digest for {asset_name}")
        if expected != f"sha256:{digest.hexdigest()}":
            fail(f"checksum mismatch for {asset_name}: expected {expected}")

        out_dir.mkdir(parents=True, exist_ok=True)
        wanted = {f"stockfish/{binary_name}": "stockfish"} | {
            f"stockfish/{doc}": doc for doc in KEEP_DOCS
        }
        with tarfile.open(archive.name) as tar:
            for member_name, target in wanted.items():
                source = tar.extractfile(member_name)
                if source is None:
                    fail(f"{member_name} is not a file in {asset_name}")
                (out_dir / target).write_bytes(source.read())
    os.chmod(out_dir / "stockfish", 0o755)
    (out_dir / "VERSION").write_text(f"{tag}\n", encoding="utf-8")
    print(f"installed {asset_name} ({tag}), {asset['digest']}")


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["resolve", version, out_file]:
            resolve(version, Path(out_file))
        case ["download", tag, arch, out_dir]:
            download(tag, arch, Path(out_dir))
        case _:
            fail(f"bad arguments: {sys.argv[1:]}")
