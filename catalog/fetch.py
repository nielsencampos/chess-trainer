"""Download the catalog TSVs at a given commit, so the vendored copy is reproducible.

Usage: uv run python -m catalog.fetch [COMMIT]   (defaults to catalog/SOURCE_COMMIT)
"""

import sys
import urllib.request
from pathlib import Path

BASE_URL = "https://raw.githubusercontent.com/lichess-org/chess-openings"
CATALOG_DIR = Path(__file__).parent
FILES = [f"{letter}.tsv" for letter in "abcde"]


def fetch(commit: str) -> None:
    data_dir = CATALOG_DIR / "data"
    data_dir.mkdir(exist_ok=True)
    for name in FILES:
        with urllib.request.urlopen(f"{BASE_URL}/{commit}/{name}", timeout=30) as response:
            (data_dir / name).write_bytes(response.read())
    (CATALOG_DIR / "SOURCE_COMMIT").write_text(f"{commit}\n", encoding="utf-8")


if __name__ == "__main__":
    default_commit = (CATALOG_DIR / "SOURCE_COMMIT").read_text(encoding="utf-8").strip()
    fetch(sys.argv[1] if len(sys.argv) > 1 else default_commit)
