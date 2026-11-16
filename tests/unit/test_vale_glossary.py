"""The Vale styles built from the glossaries (scripts/vale_glossary.py)."""

import configparser

from app.locales import load_locales
from catalog.translations import GLOSSARY_DIR
from scripts import vale_glossary


def test_the_glossary_styles_are_up_to_date():
    """Every glossary's style file matches it, and no style is left from a removed glossary."""
    files = vale_glossary.expected()
    assert files, "no glossary has words to avoid"
    for path, text in files.items():
        assert path.read_text(encoding="utf-8") == text, f"run scripts/vale_glossary.py: {path}"
    assert set(vale_glossary.STYLES.glob("Glossary*/Avoid.yml")) == set(files)


def test_each_locale_uses_its_glossary_style():
    """A locale with Vale styles lists its glossary's style for the UI and for its docs."""
    ini = configparser.ConfigParser(interpolation=None, strict=False)
    # The keys before the first section are Vale's global settings.
    ini.read_string("[global]\n" + (vale_glossary.ROOT / ".vale.ini").read_text(encoding="utf-8"))
    for locale in load_locales().values():
        if not locale.vale or not (GLOSSARY_DIR / f"{locale.code}.toml").exists():
            continue
        style = vale_glossary.style_name(locale.code)
        assert style in locale.vale, locale.code
        section = "*.md" if locale.code == "en-US" else f"*.{locale.code}.md"
        assert style in ini[section]["BasedOnStyles"], section


def test_a_word_with_regex_characters_is_escaped(tmp_path):
    """Dots and brackets match themselves; spaces and hyphens stay as they are.

    Args:
        tmp_path (Path): A temporary folder.
    """
    path = tmp_path / "pt-BR.toml"
    path.write_text(
        '[[terms]]\nterm = "x"\ntranslation = "y"\nmachine = true\navoid = ["a.b (c)", "d-e f"]\n',
        encoding="utf-8",
    )
    text = vale_glossary.rule(path)
    assert r"'a\.b \(c\)': 'y'" in text
    assert "'d-e f': 'y'" in text


def test_style_names():
    """The style is named from the locale code."""
    assert vale_glossary.style_name("pt-BR") == "GlossaryPtBR"
    assert vale_glossary.style_name("es-419") == "GlossaryEs419"
