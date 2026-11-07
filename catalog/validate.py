"""Checks every line in openings/: legal moves, and ECO and name against the catalog.

A line without an `opening` is ours (extended or imported) and only has to be legal.
Usage: uv run python -m catalog.validate [OPENINGS_DIR]
"""

import json
import sys
from pathlib import Path

from app.book.source import BookError, OpeningFile, read_opening_files, replay
from catalog.loader import index_by_position, load_catalog

LOCALES = ("en", "pt-BR", "es")
DEFAULT_DIR = Path(__file__).parent.parent / "openings"


def validate(files: list[OpeningFile], index: dict) -> list[str]:
    """Returns one message per line that disagrees with the catalog."""
    problems: list[str] = []
    for opening_file in files:
        for line in opening_file.lines:
            final_epd = replay(line).final_epd
            if line.opening is None:
                continue
            entries = index.get(final_epd, [])
            if not any(
                entry.name == line.opening and line.eco in (None, entry.eco) for entry in entries
            ):
                found = "; ".join(f"{entry.eco} {entry.name}" for entry in entries) or "nothing"
                problems.append(
                    f"{opening_file.family_id}/{line.line_id}: has {line.eco} "
                    f"{line.opening!r}, catalog has {found}"
                )
    return problems


def name_coverage(files: list[OpeningFile]) -> dict[str, dict[str, tuple[int, int]]]:
    """For each locale, how many families, subgroups and lines have their own name."""
    subgroups = {
        json.dumps(line.subgroup, sort_keys=True)
        for opening_file in files
        for line in opening_file.lines
        if line.subgroup
    }
    subgroup_names = [json.loads(item) for item in subgroups]
    line_names = [line.names for opening_file in files for line in opening_file.lines]
    family_names = [opening_file.names for opening_file in files]
    return {
        locale: {
            "families": (sum(locale in n for n in family_names), len(family_names)),
            "subgroups": (sum(locale in n for n in subgroup_names), len(subgroup_names)),
            "lines": (sum(locale in n for n in line_names), len(line_names)),
        }
        for locale in LOCALES
    }


def main(directory: Path) -> int:
    try:
        files = read_opening_files(directory)
        problems = validate(files, index_by_position(load_catalog()))
    except BookError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 1
    for problem in problems:
        print(f"INVALID: {problem}", file=sys.stderr)
    total = sum(len(opening_file.lines) for opening_file in files)
    print(f"{len(files)} families, {total} lines checked, {len(problems)} problems")
    for locale, kinds in name_coverage(files).items():
        report = ", ".join(
            f"{kind} {done}/{all_} ({done / max(all_, 1):.0%})"
            for kind, (done, all_) in kinds.items()
        )
        print(f"names {locale}: {report}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR))
