"""Help pictures and docs/HELP*.md (brief §4): in every language, and up to date."""

import re
from pathlib import Path

import pytest

from scripts import help_docs

WEB = Path(__file__).resolve().parents[2] / "web"
PICTURES = re.findall(r'data-help-img="([\w-]+)"', (WEB / "index.html").read_text())
LOCALES = sorted(path.stem for path in (WEB / "i18n").glob("*.json"))


def test_help_has_pictures():
    """Help shows pictures."""
    assert PICTURES


@pytest.mark.parametrize("locale", LOCALES)
def test_every_picture_exists_in_every_language(locale: str):
    """Every picture of Help has a file for each UI language, made by scripts/help_media.py.

    Args:
        locale (str): A language with a UI file.
    """
    missing = [name for name in PICTURES if not (WEB / "help" / locale / f"{name}.webp").is_file()]
    assert not missing, f"{locale}: run scripts/help_media.py ({missing})"


@pytest.mark.parametrize("locale", help_docs.LOCALES)
def test_help_docs_are_up_to_date(locale: str):
    """docs/HELP*.md match the Help page's strings, as scripts/help_docs.py writes them.

    Args:
        locale (str): A language of the guide.
    """
    path = help_docs.doc_path(locale)
    assert path.read_text(encoding="utf-8") == help_docs.render(locale), (
        f"{path.name} is out of date: run scripts/help_docs.py"
    )


@pytest.mark.parametrize("locale", help_docs.LOCALES)
def test_about_docs_are_up_to_date(locale: str):
    """docs/ABOUT*.md match the About page's strings, as scripts/help_docs.py writes them.

    Args:
        locale (str): A language of the About page.
    """
    path = help_docs.doc_path(locale, "ABOUT")
    assert path.read_text(encoding="utf-8") == help_docs.render_about(locale), (
        f"{path.name} is out of date: run scripts/help_docs.py"
    )


def test_help_docs_cover_every_language():
    """There is a guide for every UI language."""
    assert sorted(help_docs.LOCALES) == LOCALES
