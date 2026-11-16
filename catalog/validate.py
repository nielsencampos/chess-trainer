"""Checks every line in openings/: legal moves, and ECO and name against the catalog.

A line without an `opening` is ours (extended or imported) and only has to be legal. Also checks
the glossaries and the sources of opening names (`i18n/`), and reports, for each locale of the
registry, how many names it has and how many are sourced, rule-built, machine-translated or not
recorded yet.
Usage: uv run python -m catalog.validate [OPENINGS_DIR]
"""

import sys
from pathlib import Path

from app.book.source import BookError, OpeningFile, read_opening_files, replay
from app.locales import DEFAULT_LOCALE, load_locales
from catalog.loader import index_by_position, load_catalog
from catalog.translations import (
    NAMES_DIR,
    TranslationError,
    glossary_problems,
    load_name_sources,
    localized_names,
    name_origins,
    name_source_problems,
)

DEFAULT_DIR = Path(__file__).parent.parent / "openings"


def validate(files: list[OpeningFile], index: dict) -> list[str]:
    """Checks each line's `eco` and `opening` against the catalog, by final position.

    Every line is also replayed, so an illegal move raises.

    Args:
        files (list[OpeningFile]): The opening files.
        index (dict): The catalog by position (`index_by_position`).

    Returns:
        list[str]: One message per line that disagrees with the catalog.
    """
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
    """For each locale, how many families, subgroups and lines have their own name.

    Args:
        files (list[OpeningFile]): The opening files.

    Returns:
        dict[str, dict[str, tuple[int, int]]]: Locale -> kind -> (named, total).
    """
    # One subgroup per family and English name, as the name sources count them: two families can
    # have a subgroup of the same name.
    subgroups = {
        (opening_file.family_id, line.subgroup[DEFAULT_LOCALE]): line.subgroup
        for opening_file in files
        for line in opening_file.lines
        if line.subgroup
    }
    subgroup_names = list(subgroups.values())
    line_names = [line.names for opening_file in files for line in opening_file.lines]
    family_names = [opening_file.names for opening_file in files]
    return {
        locale: {
            "families": (sum(locale in n for n in family_names), len(family_names)),
            "subgroups": (sum(locale in n for n in subgroup_names), len(subgroup_names)),
            "lines": (sum(locale in n for n in line_names), len(line_names)),
        }
        for locale in load_locales()
    }


def translation_report(files: list[OpeningFile], names_dir: Path = NAMES_DIR) -> list[str]:
    """Checks the name sources of each locale and says where its names came from.

    Args:
        files (list[OpeningFile]): The opening files.
        names_dir (Path): The `i18n/names` folder.

    Returns:
        list[str]: One line per locale other than English, then one `INVALID:` line per problem.
            Subgroups count once per family, as their sources are recorded.
    """
    report: list[str] = []
    problems: list[str] = []
    for locale in load_locales():
        if locale == DEFAULT_LOCALE:
            continue
        names = localized_names(files, locale)
        path = names_dir / f"{locale}.toml"
        sources = {}
        if path.exists():
            try:
                sources = load_name_sources(path)
            except TranslationError as error:
                problems.append(str(error))
            problems += name_source_problems(names, sources, locale)
        counts = name_origins(names, sources)
        total = max(len(names), 1)
        report.append(
            f"sources {locale}: {len(names)} names, "
            + ", ".join(f"{origin} {n} ({n / total:.0%})" for origin, n in counts.items())
            + ("" if path.exists() else f" (no {path.name} yet)")
        )
    return report + [f"INVALID: {problem}" for problem in problems + glossary_problems()]


def main(directory: Path) -> int:
    """Validates the book and prints the problems and the name coverage.

    Args:
        directory (Path): The `openings/` folder.

    Returns:
        int: The exit code: 0 if every line agrees with the catalog.
    """
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
    translations = translation_report(files)
    for line in translations:
        print(line, file=sys.stderr if line.startswith("INVALID") else sys.stdout)
    invalid = any(line.startswith("INVALID") for line in translations)
    return 1 if problems or invalid else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR))
