"""Glossaries and opening-name sources (brief §8): their format, and that they match the book."""

import json
from pathlib import Path

import pytest

from app.book.source import read_opening_files
from app.locales import DEFAULT_LOCALE, load_locales
from catalog.translations import (
    GLOSSARY_DIR,
    NAMES_DIR,
    PIECES,
    ROOT,
    TranslationError,
    glossary_problems,
    load_glossary,
    load_name_sources,
    load_piece_letters,
    localized_names,
    name_origins,
    name_source_problems,
)
from catalog.validate import translation_report

BOOK = read_opening_files(Path(__file__).parent.parent.parent / "openings")
WIKI = "https://pt.wikipedia.org/wiki/Xeque"
FAMILY = {
    "id": "caro-kann-defense",
    "names": {"en-US": "Caro-Kann Defense", "pt-BR": "Defesa Caro-Kann"},
    "order": 1,
    "variants": [
        {
            "names": {"en-US": "Advance Variation", "pt-BR": "Variação do Avanço"},
            "lines": [
                {
                    "id": "line-0000000000000001",
                    "names": {"en-US": "Advance Variation", "pt-BR": "Variação do Avanço"},
                    "moves": ["e4", "c6", "d4", "d5", "e5"],
                    "source": "test",
                }
            ],
        }
    ],
    "lines": [
        {
            "id": "line-0000000000000002",
            "names": {"en-US": "Hillbilly Attack"},
            "moves": ["e4", "c6", "Bc4"],
            "source": "test",
        }
    ],
}
SOURCES = f"""
[families.caro-kann-defense]
name = "Defesa Caro-Kann"
source = "{WIKI}"

[subgroups.caro-kann-defense."Advance Variation"]
name = "Variação do Avanço"
rule = true

[lines.line-0000000000000001]
name = "Variação do Avanço"
machine = true
note = "no article"
"""


def write(path: Path, text: str) -> Path:
    """Writes a file.

    Args:
        path (Path): Where.
        text (str): What.

    Returns:
        Path: The path.
    """
    path.write_text(text, encoding="utf-8")
    return path


def glossary(rows: list[str]) -> str:
    """Builds a glossary file from its rows.

    Args:
        rows (list[str]): The body of each `[[terms]]` row.

    Returns:
        str: The file's text.
    """
    return "".join(f"[[terms]]\n{row}\n" for row in rows)


@pytest.fixture
def book(tmp_path):
    """A one-family book with a pt-BR family, subgroup and line name, and an English-only line.

    Args:
        tmp_path (Path): A temporary folder.

    Returns:
        list[OpeningFile]: The book.
    """
    folder = tmp_path / "openings" / "kings-pawn"
    folder.mkdir(parents=True)
    write(folder / "caro-kann-defense.json", json.dumps(FAMILY))
    return read_opening_files(tmp_path / "openings")


def test_the_glossaries_follow_the_format_and_have_the_english_terms():
    """Every glossary in i18n/glossary is valid and has the same terms as en."""
    assert glossary_problems() == []


def test_the_name_sources_match_the_book():
    """Every name-source file is for a registry locale and matches its names in openings/."""
    locales = load_locales()
    for path in sorted(NAMES_DIR.glob("*.toml")):
        assert path.stem in locales and path.stem != DEFAULT_LOCALE, path.name
        names = localized_names(BOOK, path.stem)
        assert name_source_problems(names, load_name_sources(path), path.stem) == []


def test_only_registry_locales_have_a_glossary():
    """A glossary is for a language of the registry."""
    locales = load_locales()
    assert all(path.stem in locales for path in GLOSSARY_DIR.glob("*.toml"))


def test_a_glossary_row_has_a_source_or_is_machine_translated(tmp_path):
    """Rows with a Wikipedia source, or marked as machine-translated, load.

    Args:
        tmp_path (Path): A temporary folder.
    """
    path = write(
        tmp_path / "pt-BR.toml",
        glossary(
            [
                f'term = "check"\ntranslation = "xeque"\nsource = "{WIKI}"',
                'term = "gambit"\ntranslation = "gambito"\nmachine = true\nnote = "why"',
                'term = "game"\ntranslation = "partida"\nmachine = true\navoid = ["jogo"]',
            ]
        ),
    )
    terms = load_glossary(path)
    assert terms["check"].origin == "source"
    assert terms["check"].source == WIKI
    assert terms["gambit"].origin == "machine"
    assert terms["gambit"].note == "why"
    assert terms["gambit"].avoid == ()
    assert terms["game"].avoid == ("jogo",)


@pytest.mark.parametrize(
    "row",
    [
        'term = "check"\ntranslation = "xeque"',  # no origin
        f'term = "check"\ntranslation = "xeque"\nsource = "{WIKI}"\nmachine = true',  # both
        'term = "check"\ntranslation = "xeque"\nsource = "https://example.com/xeque"',
        'term = "check"\ntranslation = "xeque"\nmachine = false',
        'term = "check"\ntranslation = "xeque"\nrule = true',  # rules are for names only
        'term = "check"\nmachine = true',  # no translation
        'term = "check"\ntranslation = "xeque"\nmachine = true\nsorce = "typo"',
        'term = "game"\ntranslation = "partida"\nmachine = true\navoid = "jogo"',  # not a list
        'term = "game"\ntranslation = "partida"\nmachine = true\navoid = [""]',
        'term = "game"\ntranslation = "partida"\nmachine = true\navoid = ["jogo", "Jogo"]',
        'term = "game"\ntranslation = "partida"\nmachine = true\navoid = ["Partida"]',
    ],
)
def test_a_bad_glossary_row_fails(tmp_path, row):
    """A row without exactly one valid origin, or with a missing or unknown field, fails.

    Args:
        tmp_path (Path): A temporary folder.
        row (str): The row.
    """
    with pytest.raises(TranslationError):
        load_glossary(write(tmp_path / "pt-BR.toml", glossary([row])))


def test_an_unknown_top_level_key_fails(tmp_path):
    """A glossary has only `terms` and `translate`.

    Args:
        tmp_path (Path): A temporary folder.
    """
    row = 'term = "check"\ntranslation = "xeque"\nmachine = true'
    with pytest.raises(TranslationError):
        load_glossary(write(tmp_path / "pt-BR.toml", "translat = []\n" + glossary([row])))


def test_a_repeated_term_fails(tmp_path):
    """A term appears once per glossary.

    Args:
        tmp_path (Path): A temporary folder.
    """
    row = 'term = "check"\ntranslation = "xeque"\nmachine = true'
    with pytest.raises(TranslationError):
        load_glossary(write(tmp_path / "pt-BR.toml", glossary([row, row])))


def test_every_glossary_has_the_english_terms(tmp_path):
    """A glossary missing a term of en, or with one en lacks, is reported.

    Args:
        tmp_path (Path): A temporary folder.
    """
    en = 'term = "{0}"\ntranslation = "{0}"\nsource = "https://en.wikipedia.org/wiki/{0}"'
    write(tmp_path / "en-US.toml", glossary([en.format("check"), en.format("draw")]))
    pt = 'term = "{0}"\ntranslation = "x"\nmachine = true'
    write(tmp_path / "pt-BR.toml", glossary([pt.format("check"), pt.format("resign")]))
    problems = glossary_problems(tmp_path)
    assert len(problems) == 2
    assert "missing terms ['draw']" in problems[0]
    assert "['resign']" in problems[1]


def test_a_glossary_needs_the_english_one(tmp_path):
    """Without en there is nothing to compare with.

    Args:
        tmp_path (Path): A temporary folder.
    """
    write(
        tmp_path / "es-419.toml",
        glossary(['term = "check"\ntranslation = "jaque"\nmachine = true']),
    )
    assert glossary_problems(tmp_path)


def test_recorded_names_match_the_book(tmp_path, book):
    """A file with an entry for each localized name, and nothing else, has no problems.

    Args:
        tmp_path (Path): A temporary folder.
        book (list[OpeningFile]): The one-family book.
    """
    names = localized_names(book, "pt-BR")
    assert len(names) == 3  # the English-only line has no pt-BR name
    sources = load_name_sources(write(tmp_path / "pt-BR.toml", SOURCES))
    assert name_source_problems(names, sources, "pt-BR") == []
    assert name_origins(names, sources) == {"source": 1, "rule": 1, "machine": 1, "unrecorded": 0}


def test_a_name_without_an_entry_or_an_entry_without_a_name_fails(tmp_path, book):
    """A missing entry, an entry for a changed name and an entry for nothing are each reported.

    Args:
        tmp_path (Path): A temporary folder.
        book (list[OpeningFile]): The one-family book.
    """
    text = (
        SOURCES.replace('[lines.line-0000000000000001]\nname = "Variação do Avanço"', "")
        .replace('name = "Defesa Caro-Kann"', 'name = "Defesa Karo-Kann"')
        .replace("machine = true\n", "")
        .replace('note = "no article"', "")
        + '\n[lines.line-0000000000000099]\nname = "Gone"\nmachine = true\n'
    )
    names = localized_names(book, "pt-BR")
    sources = load_name_sources(write(tmp_path / "pt-BR.toml", text))
    problems = name_source_problems(names, sources, "pt-BR")
    assert len(problems) == 3
    assert "Defesa Karo-Kann" in problems[0]
    assert "has no entry" in problems[1]
    assert "not in the book" in problems[2]
    assert name_origins(names, sources)["unrecorded"] == 2


@pytest.mark.parametrize(
    "text",
    [
        '[families.caro-kann-defense]\nname = "Defesa Caro-Kann"',  # no origin
        '[families.caro-kann-defense]\nname = "Defesa Caro-Kann"\nrule = true\nmachine = true',
        "[families.caro-kann-defense]\nrule = true",  # no name
        '[openings.caro-kann-defense]\nname = "Defesa Caro-Kann"\nrule = true',  # unknown kind
        '[families.caro-kann-defense]\nname = "Defesa Caro-Kann"\nsource = "http://x"',
    ],
)
def test_a_bad_name_entry_fails(tmp_path, text):
    """An entry without exactly one valid origin or without its name, or an unknown kind, fails.

    Args:
        tmp_path (Path): A temporary folder.
        text (str): The file's text.
    """
    with pytest.raises(TranslationError):
        load_name_sources(write(tmp_path / "pt-BR.toml", text))


def test_validate_reports_the_origins_per_locale(tmp_path):
    """catalog.validate has a line per locale, and an INVALID line for a bad name-source file.

    Args:
        tmp_path (Path): A temporary folder, as i18n/names.
    """
    report = translation_report(BOOK, tmp_path)
    others = [code for code in load_locales() if code != DEFAULT_LOCALE]
    assert [line.split(":")[0] for line in report] == [f"sources {code}" for code in others]
    assert all("unrecorded" in line for line in report)
    write(tmp_path / "pt-BR.toml", '[families.no-such-family]\nname = "X"\nmachine = true\n')
    assert any(
        line.startswith("INVALID") and "no-such-family" in line
        for line in translation_report(BOOK, tmp_path)
    )


# The Russian piece letters, the king with two: escaped, as they look like Latin letters.
RUSSIAN = "\u041a\u0440 \u0424 \u041b \u0421 \u041a \u041f"
PIECE_SOURCE = "https://en.wikipedia.org/wiki/Algebraic_notation_(chess)"


def pieces(letters: str, **extra: str) -> str:
    """Builds the `[[pieces]]` rows of a glossary.

    Args:
        letters (str): The letters of K, Q, R, B, N and P, separated by spaces.
        **extra (str): Raw text appended to the first row.

    Returns:
        str: The rows.
    """
    rows = []
    for index, (piece, letter) in enumerate(zip(PIECES, letters.split(), strict=True)):
        row = f'[[pieces]]\npiece = "{piece}"\nletter = "{letter}"\nsource = "{PIECE_SOURCE}"\n'
        rows.append(row + (extra.get("first", "") if index == 0 else ""))
    return "".join(rows)


def test_every_glossary_has_the_piece_letters_of_its_language():
    """Every glossary has a letter for each piece; spot-check pt-BR and de against Wikipedia."""
    for path in GLOSSARY_DIR.glob("*.toml"):
        assert list(load_piece_letters(path)) == list(PIECES), path.name
    assert "".join(load_piece_letters(GLOSSARY_DIR / "pt-BR.toml").values()) == "RDTBCP"
    assert "".join(load_piece_letters(GLOSSARY_DIR / "de.toml").values()) == "KDTLSB"


def test_piece_letters_may_have_more_than_one_character(tmp_path):
    """A multi-letter piece (the Russian king) loads.

    Args:
        tmp_path (Path): A temporary folder.
    """
    path = write(tmp_path / "pt-BR.toml", pieces(RUSSIAN))
    assert load_piece_letters(path)["K"] == RUSSIAN.split()[0]


def test_a_glossary_without_piece_letters_has_none(tmp_path):
    """No `[[pieces]]` table means English letters on screen.

    Args:
        tmp_path (Path): A temporary folder.
    """
    path = write(
        tmp_path / "pt-BR.toml", glossary(['term = "check"\ntranslation = "xeque"\nmachine = true'])
    )
    assert load_piece_letters(path) == {}


@pytest.mark.parametrize(
    "text",
    [
        pieces("R D T B C P").replace('piece = "P"', 'piece = "X"'),  # not a piece
        pieces("R D T B C P").replace('piece = "P"', 'piece = "K"'),  # K twice
        pieces("R D T B C P").split('[[pieces]]\npiece = "P"')[0],  # P missing
        pieces("R D T B C P").replace('letter = "C"', 'letter = "C C"'),  # a space
        pieces("R D T B C P", first="machine = true\n"),  # two origins
        pieces("R D T B C P", first='color = "white"\n'),  # unknown field
    ],
)
def test_bad_piece_letters_fail(tmp_path, text):
    """A bad `[[pieces]]` table is refused.

    Args:
        tmp_path (Path): A temporary folder.
        text (str): The table.
    """
    with pytest.raises(TranslationError):
        load_piece_letters(write(tmp_path / "pt-BR.toml", text))


@pytest.mark.parametrize("path", sorted(GLOSSARY_DIR.glob("*.toml")), ids=lambda path: path.stem)
def test_the_ui_file_has_the_glossary_piece_letters(path):
    """The browser reads piece letters from the UI file (`notation.pieces`): as in the glossary.

    Args:
        path (Path): A glossary.
    """
    web = ROOT / "web" / "i18n"
    strings = json.loads((web / f"{DEFAULT_LOCALE}.json").read_text(encoding="utf-8"))
    strings |= json.loads((web / f"{path.stem}.json").read_text(encoding="utf-8"))
    assert strings["notation.pieces"].split() == list(load_piece_letters(path).values())
