"""Validate every repertoire line against the catalog. Exits non-zero on any problem.

Usage: uv run python -m catalog.validate [REPERTOIRE_DIR]
"""

import sys
from pathlib import Path

from app.book.loader import Book, BookError, load_book
from catalog.loader import index_by_position, load_catalog

DEFAULT_DIR = Path(__file__).parent.parent / "repertoire"


def validate(book: Book, index: dict) -> list[str]:
    """Return one message per variation whose ECO or Opening disagrees with the catalog."""
    problems: list[str] = []
    for variant in book.variants.values():
        if variant.eco is None and variant.opening is None:
            continue
        entries = index.get(variant.final_epd, [])
        if not entries:
            problems.append(f"{variant.variant_id}: final position is not in the catalog")
            continue
        matches = [
            entry
            for entry in entries
            if variant.opening in (None, entry.name) and variant.eco in (None, entry.eco)
        ]
        if not matches:
            found = "; ".join(f"{entry.eco} {entry.name}" for entry in entries)
            problems.append(
                f"{variant.variant_id}: has {variant.eco} {variant.opening!r}, catalog has {found}"
            )
    return problems


def main(repertoire_dir: Path) -> int:
    try:
        book = load_book(repertoire_dir)
    except BookError as error:
        print(f"LOAD FAILED: {error}", file=sys.stderr)
        return 1
    problems = validate(book, index_by_position(load_catalog()))
    for problem in problems:
        print(f"INVALID: {problem}", file=sys.stderr)
    print(f"{len(book.variants)} variations checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR))
