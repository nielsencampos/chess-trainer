"""catalog.names: filling a locale's opening names, with a fake Wikipedia lookup (brief §8)."""

import json
from pathlib import Path

import pytest

from app.book.source import read_opening_files
from app.locales import Locale
from catalog.names import OfflineError, Rules, WikipediaCache, fill_names, main
from catalog.translations import (
    load_glossary,
    load_name_sources,
    localized_names,
    name_source_problems,
)

FAMILY = {
    "id": "caro-kann-defense",
    "names": {"en": "Caro-Kann Defense"},
    "order": 1,
    "variants": [
        {
            "names": {"en": "Panov Attack"},
            "lines": [
                {
                    "id": "line-0000000000000001",
                    "names": {"en": "Panov Attack"},
                    "moves": ["e4", "c6", "d4", "d5", "exd5", "cxd5", "c4"],
                    "source": "test",
                }
            ],
        },
        {
            "names": {"en": "Advance Variation"},
            "lines": [
                {
                    "id": "line-0000000000000002",
                    "names": {"en": "Advance Variation, Bayonet Attack"},
                    "moves": ["e4", "c6", "d4", "d5", "e5", "Bf5", "g4"],
                    "source": "test",
                }
            ],
        },
    ],
    "lines": [
        {
            "id": "line-0000000000000003",
            "names": {"en": "Hillbilly Attack"},
            "moves": ["e4", "c6", "Bc4"],
            "source": "test",
        }
    ],
}
GLOSSARY = """
[[terms]]
term = "{name} Attack"
translation = "Ataque {name}"
machine = true

[[terms]]
term = "Advance Variation"
translation = "Variação do Avanço"
machine = true

[[terms]]
term = "advance"
translation = "avanço"
machine = true
"""
CARO_KANN = {
    "title": "Caro-Kann Defence",
    "item": "Q1",
    "sitelinks": {"enwiki": "Caro-Kann Defence", "ptwiki": "Defesa Caro-Kann (xadrez)"},
    "labels": {"en": "Caro-Kann Defence", "pt": "defesa Caro-Kann"},
}
PANOV = {
    "title": "Caro-Kann Defence, Panov Attack",
    "item": "Q2",
    "sitelinks": {"enwiki": "Caro-Kann Defence, Panov Attack"},
    "labels": {"pt": "Defesa Caro-Kann, Ataque Panov-Botvinnik"},
}
LOOKUPS = {
    "Caro-Kann Defense": CARO_KANN,
    "Caro-Kann Defense, Panov Attack": PANOV,
    # A redirect to the family's own article says nothing about the subgroup.
    "Caro-Kann Defense, Advance Variation": CARO_KANN,
}


class FakeRemote:
    """A Wikipedia lookup from a dictionary, counting the titles asked for."""

    def __init__(self, entries: dict) -> None:
        """Creates the lookup.

        Args:
            entries (dict): The entry for each title; a title not in it has no article.
        """
        self.entries = entries
        self.asked: list[str] = []

    def fetch(self, titles: list[str]) -> dict:
        """Looks titles up.

        Args:
            titles (list[str]): English titles.

        Returns:
            dict: The entry of each, or None.
        """
        self.asked += titles
        return {title: self.entries.get(title) for title in titles}


def locale(reviewed: bool = False) -> Locale:
    """A Brazilian Portuguese locale.

    Args:
        reviewed (bool): Whether the author reviews it.

    Returns:
        Locale: The locale.
    """
    return Locale("pt-BR", "ltr", ("latin",), None, (), reviewed, "pt")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A book of one family, a glossary and empty name sources.

    Args:
        tmp_path (Path): A temporary folder.

    Returns:
        Path: The folder, with `openings/`, `glossary/`, `names/` and `machine/`.
    """
    (tmp_path / "openings").mkdir()
    write_family(tmp_path, FAMILY)
    (tmp_path / "glossary").mkdir()
    (tmp_path / "glossary" / "pt-BR.toml").write_text(GLOSSARY, encoding="utf-8")
    return tmp_path


def write_family(root: Path, document: dict) -> None:
    """Writes the family's opening file.

    Args:
        root (Path): The test folder.
        document (dict): The file's content.
    """
    path = root / "openings" / "caro-kann-defense.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(root: Path, remote: FakeRemote | None, **options: bool) -> object:
    """Fills pt-BR in the test folder.

    Args:
        root (Path): The test folder.
        remote (FakeRemote | None): The lookup; None is offline.
        **options (bool): `reviewed` and `overwrite`.

    Returns:
        object: The run's report.
    """
    cache = WikipediaCache(root / "wikipedia.json", remote)
    return fill_names(
        locale(options.get("reviewed", False)),
        cache,
        openings_dir=root / "openings",
        glossary_dir=root / "glossary",
        names_dir=root / "names",
        machine_dir=root / "machine",
        overwrite=options.get("overwrite", False),
    )


def names(root: Path) -> dict:
    """The book's pt-BR names.

    Args:
        root (Path): The test folder.

    Returns:
        dict: The names by kind and key.
    """
    return localized_names(read_opening_files(root / "openings"), "pt-BR")


def test_wikipedia_then_glossary_then_machine(repo):
    """Each name takes the first origin that has it, and every name is recorded.

    Args:
        repo (Path): The test folder.
    """
    report = run(repo, FakeRemote(LOOKUPS))
    book = names(repo)
    sources = load_name_sources(repo / "names" / "pt-BR.toml")
    family = sources[("families", ("caro-kann-defense",))]
    assert book[("families", ("caro-kann-defense",))] == "Defesa Caro-Kann"
    assert family.source == "https://pt.wikipedia.org/wiki/Defesa_Caro-Kann_(xadrez)"
    # The Wikidata label, without the family's name before it.
    panov = sources[("subgroups", ("caro-kann-defense", "Panov Attack"))]
    assert panov.name == "Ataque Panov-Botvinnik"
    assert panov.source == "https://www.wikidata.org/wiki/Q2"
    # The redirect to the family is ignored; the glossary builds it, the proper name kept.
    assert sources[("subgroups", ("caro-kann-defense", "Advance Variation"))].origin == "rule"
    line = sources[("lines", ("line-0000000000000002",))]
    assert (line.name, line.origin) == ("Variação do Avanço, Ataque Bayonet", "rule")
    assert ("lines", ("line-0000000000000003",)) in sources
    assert name_source_problems(book, sources, "pt-BR") == []
    assert report.counts["source"] == 3  # The family, Panov, and its line of the same name.
    assert report.todo == 0
    assert report.proper == {"Bayonet": 1, "Hillbilly": 1}


def test_untranslatable_names_wait_for_machine_translation(repo):
    """A name the glossary does not cover is listed, and enters the book once filled in.

    Args:
        repo (Path): The test folder.
    """
    (repo / "glossary" / "pt-BR.toml").write_text(
        GLOSSARY.replace("{name} Attack", "{name} Gambit"), encoding="utf-8"
    )
    report = run(repo, FakeRemote({}))
    machine = repo / "machine" / "pt-BR.toml"
    assert report.todo == 5  # All but "Advance Variation", which is a term.
    assert ("lines", ("line-0000000000000003",)) not in names(repo)
    text = machine.read_text(encoding="utf-8")
    assert '[lines.line-0000000000000003]\nen = "Hillbilly Attack"\nname = ""' in text
    machine.write_text(
        text.replace('Hillbilly Attack"\nname = ""', 'Hillbilly Attack"\nname = "Ataque Caipira"'),
        encoding="utf-8",
    )
    report = run(repo, None)
    entry = load_name_sources(repo / "names" / "pt-BR.toml")[("lines", ("line-0000000000000003",))]
    assert (entry.name, entry.origin) == ("Ataque Caipira", "machine")
    assert report.todo == 4
    assert "line-0000000000000003" not in machine.read_text(encoding="utf-8")


def test_reruns_are_offline_and_change_nothing(repo):
    """The cache answers a second run without the internet, with the same files.

    Args:
        repo (Path): The test folder.
    """
    remote = FakeRemote(LOOKUPS)
    run(repo, remote)
    assert len(remote.asked) == 5  # One per distinct title, missing ones included.
    files = sorted(path for path in repo.rglob("*") if path.is_file())
    before = {path: path.read_bytes() for path in files}
    report = run(repo, None)
    assert report.changed_files == 0
    assert {path: path.read_bytes() for path in files} == before


def test_offline_without_a_cache_fails(repo):
    """A lookup the cache lacks is an error offline, and nothing is written.

    Args:
        repo (Path): The test folder.
    """
    with pytest.raises(OfflineError):
        run(repo, None)
    assert not (repo / "names").exists()


def test_a_reviewed_locale_keeps_its_names(repo):
    """Reviewed names stay; matching origins are recorded, and differences listed.

    Args:
        repo (Path): The test folder.
    """
    document = json.loads(json.dumps(FAMILY))
    document["names"]["pt-BR"] = "Defesa caro-kann"
    document["variants"][0]["names"]["pt-BR"] = "Ataque Panov"
    document["variants"][1]["names"]["pt-BR"] = "Variação do Avanço"
    document["lines"][0]["names"]["pt-BR"] = "Ataque dos Caipiras"
    write_family(repo, document)
    report = run(repo, FakeRemote(LOOKUPS), reviewed=True)
    book, sources = names(repo), load_name_sources(repo / "names" / "pt-BR.toml")
    assert book[("families", ("caro-kann-defense",))] == "Defesa caro-kann"
    assert sources[("families", ("caro-kann-defense",))].origin == "source"
    # Wikipedia differs, so it is listed; the glossary gives the same name, so it is recorded.
    assert book[("subgroups", ("caro-kann-defense", "Panov Attack"))] == "Ataque Panov"
    assert sum("Ataque Panov-Botvinnik" in line for line in report.differs) == 1
    assert sources[("subgroups", ("caro-kann-defense", "Panov Attack"))].origin == "rule"
    # No origin gives "Ataque dos Caipiras": it stays, unrecorded.
    assert book[("lines", ("line-0000000000000003",))] == "Ataque dos Caipiras"
    assert ("lines", ("line-0000000000000003",)) not in sources
    assert report.counts["unrecorded"] == 1
    # A name the locale does not have yet is filled.
    assert book[("lines", ("line-0000000000000002",))] == "Variação do Avanço, Ataque Bayonet"
    problems = name_source_problems(book, sources, "pt-BR")
    assert problems == [
        "pt-BR.toml: lines.line-0000000000000003: 'Ataque dos Caipiras' has no entry"
    ]

    run(repo, None, reviewed=True, overwrite=True)
    book = names(repo)
    assert book[("subgroups", ("caro-kann-defense", "Panov Attack"))] == "Ataque Panov-Botvinnik"
    assert book[("lines", ("line-0000000000000003",))] == "Ataque Hillbilly"


def test_a_sourced_name_is_never_replaced(repo):
    """In a locale that is not reviewed, a name with a source stays as it is.

    Args:
        repo (Path): The test folder.
    """
    document = json.loads(json.dumps(FAMILY))
    document["lines"][0]["names"]["pt-BR"] = "Ataque Caipira"
    write_family(repo, document)
    (repo / "names").mkdir()
    (repo / "names" / "pt-BR.toml").write_text(
        '[lines.line-0000000000000003]\nname = "Ataque Caipira"\n'
        'source = "https://pt.wikipedia.org/wiki/Ataque_Caipira"\nnote = "kept"\n',
        encoding="utf-8",
    )
    run(repo, FakeRemote(LOOKUPS))
    entry = load_name_sources(repo / "names" / "pt-BR.toml")[("lines", ("line-0000000000000003",))]
    assert (entry.name, entry.origin, entry.note) == ("Ataque Caipira", "source", "kept")


def test_english_is_refused(repo):
    """English is the source of every name, so there is nothing to fill.

    Args:
        repo (Path): The test folder.
    """
    english = Locale("en", "ltr", ("latin",), None, (), True, "en")
    with pytest.raises(ValueError):
        fill_names(english, WikipediaCache(repo / "wikipedia.json", None))
    assert main(["en", "--offline"]) == 1


@pytest.mark.parametrize(
    ("english", "expected"),
    [
        ("Panov Attack", "Ataque Panov"),
        ("Panov-Botvinnik Attack", "Ataque Panov-Botvinnik"),
        ("Advance Variation, Panov Attack", "Variação do Avanço, Ataque Panov"),
        ("ADVANCE VARIATION", "Variação do Avanço"),
        ("Advance Attack", None),  # "Advance" is a glossary word, not a proper name.
        ("quick Attack", None),  # Not capitalized.
        ("Panov Attack, Main Line", None),  # One segment is not covered: none is.
    ],
)
def test_rules_translate_segment_by_segment(tmp_path, english, expected):
    """Every segment is a term, or a template around a proper name.

    Args:
        tmp_path (Path): A temporary folder.
        english (str): An English name.
        expected (str | None): Its translation, or None.
    """
    path = tmp_path / "pt-BR.toml"
    path.write_text(GLOSSARY, encoding="utf-8")
    assert Rules(load_glossary(path)).translate(english) == expected
