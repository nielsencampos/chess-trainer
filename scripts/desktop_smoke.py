"""Smoke check of a desktop build: it serves, stays up and its window shows the app.

Starts it, asks the health endpoint, checks it stays up and that its window left the starting
page for the app (a line in the app's log), then closes it.

Usage: python scripts/desktop_smoke.py EXECUTABLE

Stdlib only, so it runs the same on Linux, Windows and macOS. The app keeps its log in the
user's data folder; on a failure this prints its end.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:47800/api/health"
START_TIMEOUT_S = 120  # the first launch of a fresh build is slow on CI runners
STAY_UP_S = 10  # the window opens after the server answers; a broken GUI exits here
LOGS = {
    "linux": "~/.local/share/chess-trainer/chess-trainer.log",
    "darwin": "~/Library/Application Support/chess-trainer/chess-trainer.log",
    "win32": os.path.join(os.environ.get("LOCALAPPDATA", ""), "chess-trainer", "chess-trainer.log"),
}


def health() -> dict | None:
    """Reads the health endpoint once.

    Returns:
        dict | None: The answer, or None if nothing answers yet.
    """
    try:
        # No proxy for loopback, as in desktop/launcher.py.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL, timeout=5) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None


SHOWN = "the window shows the app"  # logged by desktop/launcher.py after loading the app's page


def log_path() -> Path:
    """The app's log file on this system.

    Returns:
        Path: The file, which may not exist yet.
    """
    return Path(os.path.expanduser(LOGS.get(sys.platform, "")))


def log_since(offset: int) -> str:
    """The app's log written after a point.

    Args:
        offset (int): The log's size in bytes at that point.

    Returns:
        str: The text, empty if there is no log.
    """
    log = log_path()
    if not log.is_file():
        return ""
    with log.open("rb") as file:
        file.seek(offset)
        return file.read().decode("utf-8", errors="replace")


def print_log() -> None:
    """Prints the end of the app's log, if there is one."""
    log = log_path()
    if log.is_file():
        print(f"--- {log} ---")
        print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]))


def main(executable: str) -> int:
    """Runs the check.

    Args:
        executable (str): The built program.

    Returns:
        int: 0 on success, 1 on a failure.
    """
    if health() is not None:
        print(f"something already answers on {URL}")
        return 1
    log = log_path()
    offset = log.stat().st_size if log.is_file() else 0
    process = subprocess.Popen([executable])
    try:
        deadline = time.monotonic() + START_TIMEOUT_S
        answer = None
        while answer is None and time.monotonic() < deadline:
            if process.poll() is not None:
                print(f"the app exited with code {process.returncode} before serving")
                print_log()
                return 1
            time.sleep(1)
            answer = health()
        if answer is None:
            print(f"no answer on {URL} after {START_TIMEOUT_S} s")
            print_log()
            return 1
        print(json.dumps(answer))
        engine = answer.get("engine", {})
        if not str(engine.get("name", "")).startswith("Stockfish") or not engine.get("build_tag"):
            print("the bundled Stockfish did not start, or its VERSION file is missing")
            print_log()
            return 1
        time.sleep(STAY_UP_S)
        if process.poll() is not None:
            print(f"the app exited with code {process.returncode} after serving")
            print_log()
            return 1
        if SHOWN not in log_since(offset):
            print("the window did not leave the starting page for the app")
            print_log()
            return 1
        print("ok: the app serves, stays up and its window shows it")
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
