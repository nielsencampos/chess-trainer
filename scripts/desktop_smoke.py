"""Smoke check of a desktop build: start it, ask the health endpoint, check it stays up, close it.

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
        with urllib.request.urlopen(URL, timeout=5) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def print_log() -> None:
    """Prints the end of the app's log, if there is one."""
    log = Path(os.path.expanduser(LOGS.get(sys.platform, "")))
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
        print("ok: the app serves and stays up")
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
