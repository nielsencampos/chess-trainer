"""Where translations come from: the chess glossaries and the sources of opening names.

`i18n/glossary/{locale}.toml` lists the chess terms the UI uses, translated, with the
Wikipedia or Wikidata page each came from, or `machine = true` when none was found, and the words
the UI must not use for that term (`avoid`), plus an optional top-level `translate` list: words
of the English opening names that the language translates, so a glossary rule never keeps them as
proper names, and a `[[pieces]]` table: the letter of each piece in that language, for the
"local letters" move notation (#53).
`i18n/names/{locale}.toml` records, for each localized family, subgroup and line name in
`openings/`, where it came from: a Wikipedia or Wikidata page (`source`), the glossary, segment
by segment (`rule = true`), or machine translation (`machine = true`). The names themselves stay
in the `names` of the opening files (brief §6, §8).
"""

import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.book.source import OpeningFile
from app.locales import DEFAULT_LOCALE

ROOT = Path(__file__).parent.parent
GLOSSARY_DIR = ROOT / "i18n" / "glossary"
NAMES_DIR = ROOT / "i18n" / "names"
# A page of any language's Wikipedia, or a Wikidata item.
SOURCE_URL = re.compile(
    r"^https://(?:[a-z0-9-]+\.(?:m\.)?wikipedia\.org/wiki/|www\.wikidata\.org/wiki/)\S+$"
)
ORIGINS = ("source", "rule", "machine")
GLOSSARY_FIELDS = {"term", "translation", "source", "machine", "note", "avoid"}
PIECE_FIELDS = {"piece", "letter", "source", "machine", "note"}
# The English SAN letters, in the order the web app's `notation.pieces` key lists them.
PIECES = ("K", "Q", "R", "B", "N", "P")
NAME_FIELDS = {"name", "source", "rule", "machine", "note"}
KINDS = ("families", "subgroups", "lines")
# A localized name: its kind and its key (family id, family id and English subgroup name, or
# line id).
NameKey = tuple[str, tuple[str, ...]]


class TranslationError(ValueError):
    """A glossary or name-source file that does not follow its format."""


@dataclass(frozen=True)
class Term:
    """One row of a glossary.

    Attributes:
        term (str): The English term, as in the `en` glossary.
        translation (str): The term in the glossary's language.
        origin (str): `source` or `machine`.
        source (str | None): The Wikipedia or Wikidata URL, for `source`.
        note (str | None): Why a choice was made, if one was.
        avoid (tuple[str, ...]): Words the UI must not use for this term, such as an older
            translation or a synonym.
    """

    term: str
    translation: str
    origin: str
    source: str | None = None
    note: str | None = None
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class NameSource:
    """Where one localized opening name came from.

    Attributes:
        name (str): The name it was recorded for, as in `openings/`.
        origin (str): `source`, `rule` or `machine`.
        source (str | None): The Wikipedia or Wikidata URL, for `source`.
        note (str | None): Why a choice was made, if one was.
    """

    name: str
    origin: str
    source: str | None = None
    note: str | None = None


def _origin(entry: dict, where: str, allowed: tuple[str, ...]) -> tuple[str, str | None]:
    """Reads an entry's origin: exactly one of `source`, and `rule` or `machine` set to true.

    Args:
        entry (dict): The raw entry.
        where (str): The file and entry, for the error message.
        allowed (tuple[str, ...]): The origins this kind of file accepts.

    Returns:
        tuple[str, str | None]: The origin, and the source URL when it is `source`.

    Raises:
        TranslationError: No origin, more than one, a flag that is not `true`, or a source that
            is not a Wikipedia or Wikidata page.
    """
    given = [origin for origin in allowed if origin in entry]
    if len(given) != 1:
        raise TranslationError(f"{where}: needs exactly one of {', '.join(allowed)}")
    origin = given[0]
    if origin == "source":
        if not isinstance(entry["source"], str) or not SOURCE_URL.match(entry["source"]):
            raise TranslationError(f"{where}: source must be a Wikipedia or Wikidata URL")
        return origin, entry["source"]
    if entry[origin] is not True:
        raise TranslationError(f"{where}: {origin} must be true, or left out")
    return origin, None


def _text(entry: dict, field: str, where: str) -> str:
    """Reads a required, non-empty text field.

    Args:
        entry (dict): The raw entry.
        field (str): The field's name.
        where (str): The file and entry, for the error message.

    Returns:
        str: The text.

    Raises:
        TranslationError: The field is missing, empty or not text.
    """
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TranslationError(f"{where}: {field} must be non-empty text")
    return value


def _avoid(entry: dict, where: str) -> tuple[str, ...]:
    """Reads a term's optional `avoid` list.

    Args:
        entry (dict): The raw entry.
        where (str): The file and entry, for the error message.

    Returns:
        tuple[str, ...]: The words to avoid; empty when the field is left out.

    Raises:
        TranslationError: The field is not a list of non-empty texts, repeats a word, or lists the
            translation itself.
    """
    words = entry.get("avoid", [])
    if not isinstance(words, list) or not all(
        isinstance(word, str) and word.strip() for word in words
    ):
        raise TranslationError(f"{where}: avoid must be a list of non-empty texts")
    folded = [word.casefold() for word in words]
    if len(set(folded)) != len(folded):
        raise TranslationError(f"{where}: avoid repeats a word")
    if str(entry.get("translation", "")).casefold() in folded:
        raise TranslationError(f"{where}: avoid lists the translation itself")
    return tuple(words)


def load_glossary(path: Path) -> dict[str, Term]:
    """Reads a glossary: a `[[terms]]` table per chess term.

    Args:
        path (Path): An `i18n/glossary/{locale}.toml` file.

    Returns:
        dict[str, Term]: The rows by English term, in the file's order.

    Raises:
        TranslationError: A row has an unknown or missing field, no origin or a bad one, a bad
            `avoid` list, or repeats a term.
    """
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    if unknown := set(document) - {"terms", "translate", "pieces"}:
        raise TranslationError(f"{path.name}: unknown tables or keys {sorted(unknown)}")
    rows = document.get("terms", [])
    terms: dict[str, Term] = {}
    for n, row in enumerate(rows, 1):
        where = f"{path.name}: terms #{n}"
        if unknown := set(row) - GLOSSARY_FIELDS:
            raise TranslationError(f"{where}: unknown fields {sorted(unknown)}")
        term = _text(row, "term", where)
        if term in terms:
            raise TranslationError(f"{where}: {term!r} is already in the glossary")
        origin, source = _origin(row, f"{where} ({term})", ("source", "machine"))
        terms[term] = Term(
            term,
            _text(row, "translation", where),
            origin,
            source,
            row.get("note"),
            _avoid(row, f"{where} ({term})"),
        )
    return terms


def load_translate_words(path: Path) -> frozenset[str]:
    """Reads a glossary's `translate` list: English words its language translates in names.

    They are words of the English opening names that are not proper names in that language
    ("Exchange", "Vienna"), so a `{name}` rule does not keep them.

    Args:
        path (Path): An `i18n/glossary/{locale}.toml` file.

    Returns:
        frozenset[str]: The words, case-folded; empty when the file has no list.

    Raises:
        TranslationError: The list is not made of non-empty single words, or repeats one.
    """
    with path.open("rb") as handle:
        words = tomllib.load(handle).get("translate", [])
    where = f"{path.name}: translate"
    if not isinstance(words, list) or not all(
        isinstance(word, str) and word.strip() and not re.search(r"[\s,]", word) for word in words
    ):
        raise TranslationError(f"{where} must be a list of single words")
    folded = [word.casefold() for word in words]
    if len(set(folded)) != len(folded):
        raise TranslationError(f"{where} repeats a word")
    return frozenset(folded)


def load_piece_letters(path: Path) -> dict[str, str]:
    """Reads a glossary's `[[pieces]]` table: the letter of each piece in its language.

    Args:
        path (Path): An `i18n/glossary/{locale}.toml` file.

    Returns:
        dict[str, str]: English SAN letter (K, Q, R, B, N, P) -> the language's letter, in that
            order; empty when the file has no table, so the language shows English letters.

    Raises:
        TranslationError: A row has an unknown or missing field, no origin or a bad one, a
            letter with a space, a piece that is not one of K, Q, R, B, N, P, or the table does
            not have each piece once.
    """
    with path.open("rb") as handle:
        rows = tomllib.load(handle).get("pieces", [])
    letters: dict[str, str] = {}
    for n, row in enumerate(rows, 1):
        where = f"{path.name}: pieces #{n}"
        if unknown := set(row) - PIECE_FIELDS:
            raise TranslationError(f"{where}: unknown fields {sorted(unknown)}")
        piece = _text(row, "piece", where)
        if piece not in PIECES:
            raise TranslationError(f"{where}: {piece!r} is not one of {', '.join(PIECES)}")
        if piece in letters:
            raise TranslationError(f"{where}: {piece!r} is already in the table")
        letter = _text(row, "letter", where)
        if re.search(r"\s", letter):
            raise TranslationError(f"{where}: the letter {letter!r} has a space")
        _origin(row, f"{where} ({piece})", ("source", "machine"))
        letters[piece] = letter
    if letters and set(letters) != set(PIECES):
        missing = [piece for piece in PIECES if piece not in letters]
        raise TranslationError(f"{path.name}: pieces lacks {missing}")
    return {piece: letters[piece] for piece in PIECES if piece in letters}


def glossary_problems(directory: Path = GLOSSARY_DIR) -> list[str]:
    """Checks every glossary, and that each has the same terms as the English one.

    Args:
        directory (Path): The `i18n/glossary` folder.

    Returns:
        list[str]: One message per problem; empty when there is none.
    """
    problems: list[str] = []
    glossaries: dict[str, dict[str, Term]] = {}
    for path in sorted(directory.glob("*.toml")):
        try:
            glossaries[path.stem] = load_glossary(path)
            load_translate_words(path)
            load_piece_letters(path)
        except TranslationError as error:
            problems.append(str(error))
    if not glossaries:
        return problems
    english = glossaries.get(DEFAULT_LOCALE)
    if english is None:
        return [*problems, f"{directory.name}: there is no {DEFAULT_LOCALE}.toml to compare with"]
    for locale, terms in glossaries.items():
        if missing := [term for term in english if term not in terms]:
            problems.append(f"{locale}.toml: missing terms {missing}")
        if extra := [term for term in terms if term not in english]:
            problems.append(f"{locale}.toml: terms not in {DEFAULT_LOCALE}.toml {extra}")
    return problems


def localized_names(files: list[OpeningFile], locale: str) -> dict[NameKey, str]:
    """Collects every name the book has in a locale.

    Args:
        files (list[OpeningFile]): The opening files.
        locale (str): The locale.

    Returns:
        dict[NameKey, str]: The name by kind and key: `families` by family id, `subgroups` by
            family id and English name, `lines` by line id.
    """
    names: dict[NameKey, str] = {}
    for opening_file in files:
        if locale in opening_file.names:
            names[("families", (opening_file.family_id,))] = opening_file.names[locale]
        for line in opening_file.lines:
            if line.subgroup and locale in line.subgroup:
                key = (opening_file.family_id, line.subgroup[DEFAULT_LOCALE])
                names[("subgroups", key)] = line.subgroup[locale]
            if locale in line.names:
                names[("lines", (line.line_id,))] = line.names[locale]
    return names


def load_name_sources(path: Path) -> dict[NameKey, NameSource]:
    """Reads a name-source file.

    Families are `[families.<family id>]`, subgroups `[subgroups.<family id>."<English name>"]`
    and lines `[lines.<line id>]`, each with the `name` it was recorded for and its origin.

    Args:
        path (Path): An `i18n/names/{locale}.toml` file.

    Returns:
        dict[NameKey, NameSource]: The entries by kind and key.

    Raises:
        TranslationError: A kind is unknown, or an entry has an unknown or missing field, or no
            origin or a bad one.
    """
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    if unknown := set(raw) - set(KINDS):
        raise TranslationError(f"{path.name}: unknown tables {sorted(unknown)}")
    flat: list[tuple[NameKey, dict]] = []
    for family_id, entry in raw.get("families", {}).items():
        flat.append((("families", (family_id,)), entry))
    for family_id, subgroups in raw.get("subgroups", {}).items():
        for english, entry in subgroups.items():
            flat.append((("subgroups", (family_id, english)), entry))
    for line_id, entry in raw.get("lines", {}).items():
        flat.append((("lines", (line_id,)), entry))
    sources: dict[NameKey, NameSource] = {}
    for key, entry in flat:
        where = f"{path.name}: {key[0]}.{'.'.join(key[1])}"
        if not isinstance(entry, dict):
            raise TranslationError(f"{where}: must be a table")
        if unknown := set(entry) - NAME_FIELDS:
            raise TranslationError(f"{where}: unknown fields {sorted(unknown)}")
        origin, source = _origin(entry, where, ORIGINS)
        sources[key] = NameSource(_text(entry, "name", where), origin, source, entry.get("note"))
    return sources


def name_source_problems(
    names: dict[NameKey, str], sources: dict[NameKey, NameSource], locale: str
) -> list[str]:
    """Checks that each localized name has an entry, and each entry a name it matches.

    Args:
        names (dict[NameKey, str]): The locale's names (`localized_names`).
        sources (dict[NameKey, NameSource]): The locale's name sources.
        locale (str): The locale, for the messages.

    Returns:
        list[str]: One message per problem; empty when there is none.
    """
    problems: list[str] = []
    for key, name in names.items():
        label = f"{locale}.toml: {key[0]}.{'.'.join(key[1])}"
        if key not in sources:
            problems.append(f"{label}: {name!r} has no entry")
        elif sources[key].name != name:
            problems.append(f"{label}: entry is for {sources[key].name!r}, the book has {name!r}")
    for key, source in sources.items():
        if key not in names:
            problems.append(
                f"{locale}.toml: {key[0]}.{'.'.join(key[1])}: {source.name!r} is not in the book"
            )
    return problems


def name_origins(names: dict[NameKey, str], sources: dict[NameKey, NameSource]) -> Counter[str]:
    """Counts a locale's names by origin.

    Args:
        names (dict[NameKey, str]): The locale's names (`localized_names`).
        sources (dict[NameKey, NameSource]): The locale's name sources; empty when it has none.

    Returns:
        Counter[str]: `source`, `rule`, `machine`, and `unrecorded` for a name with no entry,
            or whose entry is for another name.
    """
    counts: Counter[str] = Counter({origin: 0 for origin in (*ORIGINS, "unrecorded")})
    for key, name in names.items():
        entry = sources.get(key)
        counts[entry.origin if entry and entry.name == name else "unrecorded"] += 1
    return counts
