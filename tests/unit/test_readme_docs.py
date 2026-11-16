"""README*.md and HOW_TO_INSTALL*.md: written from i18n/docs/, complete, with working links."""

import json
import re
import unicodedata

import pytest

from app.locales import DEFAULT_LOCALE
from scripts import readme_docs

LINK = re.compile(r"\]\(([^)\s]+)\)")
PAIRS = [(doc, locale) for doc in readme_docs.DOCS for locale in readme_docs.LOCALES]
ENGLISH = json.loads((readme_docs.SOURCE / f"{DEFAULT_LOCALE}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(("doc", "locale"), PAIRS)
def test_docs_are_up_to_date(doc: str, locale: str):
    """Each doc matches its template and strings, as scripts/readme_docs.py writes it.

    Args:
        doc (str): `README` or `HOW_TO_INSTALL`.
        locale (str): A UI language.
    """
    path = readme_docs.path_of(doc, locale)
    assert path.read_text(encoding="utf-8") == readme_docs.render(doc, locale), (
        f"{path.name} is out of date: run scripts/readme_docs.py"
    )


@pytest.mark.parametrize("path", sorted(readme_docs.SOURCE.glob("*.json")), ids=lambda p: p.stem)
def test_strings_have_the_english_keys(path):
    """A strings file has every English key, and no other; en-GB holds only what differs.

    Args:
        path (Path): An `i18n/docs/{locale}.json` file.
    """
    assert path.stem in readme_docs.LOCALES, f"{path.name}: no such UI language"
    keys = set(json.loads(path.read_text(encoding="utf-8")))
    assert keys <= set(ENGLISH), f"{path.name}: unknown keys {sorted(keys - set(ENGLISH))}"
    if path.stem != "en-GB":
        assert keys == set(ENGLISH), f"{path.name}: missing {sorted(set(ENGLISH) - keys)}"


@pytest.mark.parametrize("path", sorted(readme_docs.SOURCE.glob("*.json")), ids=lambda p: p.stem)
def test_strings_name_only_known_targets(path):
    """A `{token}` in a string is one the script fills, and it is the same as in English.

    Args:
        path (Path): An `i18n/docs/{locale}.json` file.
    """
    for key, text in json.loads(path.read_text(encoding="utf-8")).items():
        tokens = re.findall(r"\{[^{}]*\}", text)
        assert all(readme_docs.TOKEN.fullmatch(token) for token in tokens), (key, tokens)
        assert sorted(tokens) == sorted(re.findall(r"\{[^{}]*\}", ENGLISH[key])), key


def test_templates_use_existing_keys():
    """Every `{{key}}` of a template has an English string."""
    for doc in readme_docs.DOCS:
        template = (readme_docs.SOURCE / f"{doc}.md").read_text(encoding="utf-8")
        keys = set(readme_docs.TEMPLATE_KEY.findall(template)) - {"languages", "notice"}
        assert keys <= set(ENGLISH), sorted(keys - set(ENGLISH))


@pytest.mark.parametrize(("doc", "locale"), PAIRS)
def test_relative_links_work(doc: str, locale: str):
    """Every relative link of a doc points at a file, and its anchor at one of its headings.

    Args:
        doc (str): `README` or `HOW_TO_INSTALL`.
        locale (str): A UI language.
    """
    path = readme_docs.path_of(doc, locale)
    for target in LINK.findall(readme_docs.render(doc, locale)):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        file, _, anchor = target.partition("#")
        linked = path.parent / file if file else path
        assert linked.exists(), f"{path.name}: {target}"
        if anchor and linked.suffix == ".md":
            headings = re.findall(r"^#+ (.*)$", linked.read_text(encoding="utf-8"), re.MULTILINE)
            assert anchor in {readme_docs.anchor(h) for h in headings}, f"{path.name}: {target}"


def _flanks(text: str, start: int, end: int) -> tuple[bool, bool]:
    """Whether a run of `*` can open and close emphasis, by CommonMark's flanking rules.

    Args:
        text (str): The text.
        start (int): Where the run starts.
        end (int): Where it ends.

    Returns:
        tuple[bool, bool]: Left-flanking (it can open) and right-flanking (it can close).
    """
    before = text[start - 1] if start else " "
    after = text[end] if end < len(text) else " "

    def punct(char: str) -> bool:
        """Whether a character is punctuation or a symbol.

        Args:
            char (str): The character.

        Returns:
            bool: True for Unicode categories P and S.
        """
        return unicodedata.category(char)[0] in "PS"

    left = not after.isspace() and (not punct(after) or before.isspace() or punct(before))
    right = not before.isspace() and (not punct(before) or after.isspace() or punct(after))
    return left, right


@pytest.mark.parametrize("path", sorted(readme_docs.SOURCE.glob("*.json")), ids=lambda p: p.stem)
def test_bold_and_italics_open_and_close(path):
    """Every `**` and `*` of a string opens or closes as meant, CJK punctuation included.

    A closing `**` after punctuation, such as a full-width colon, and before a letter stays as
    text on GitHub.

    Args:
        path (Path): An `i18n/docs/{locale}.json` file.
    """
    for key, text in json.loads(path.read_text(encoding="utf-8")).items():
        prose = re.sub(r"`[^`]*`", "`x`", text)
        runs = list(re.finditer(r"\*+", prose))
        for marker in ("**", "*"):
            mine = [run for run in runs if run.group() == marker]
            assert all(len(run.group()) <= 2 for run in runs), (key, prose)
            for n, run in enumerate(mine):
                left, right = _flanks(prose, run.start(), run.end())
                assert right if n % 2 else left, (
                    key,
                    prose[max(0, run.start() - 15) : run.end() + 15],
                )


def test_every_language_has_its_strings():
    """Every UI language has its doc strings: no doc falls back to English as a whole."""
    have = {path.stem for path in readme_docs.SOURCE.glob("*.json")}
    assert have == set(readme_docs.LOCALES), sorted(set(readme_docs.LOCALES) ^ have)
