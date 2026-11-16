"""The locale registry, i18n/locales.toml (brief §8): one entry per UI file, and valid values."""

import json
import re
import unicodedata
from pathlib import Path

import pytest

from app.locales import DEFAULT_LOCALE, load_locales

WEB = Path(__file__).parent.parent.parent / "web"
I18N_DIR = WEB / "i18n"
# The UI font of a script: Familjen Grotesk has no Cyrillic, so Commissioner draws it (brief §4.1).
UI_FONT = {"cyrillic": "commissioner"}
FACE = re.compile(
    r'url\("\.\./fonts/(familjen-grotesk|commissioner|jetbrains-mono)-([a-z-]+)-(\d+)-normal\.woff2"\)'
    r".*?unicode-range: ([^;]+);",
    re.S,
)
GOOD = """
[locales.en-US]
direction = "ltr"
scripts = ["latin"]
reviewed = true
"""


def test_every_ui_file_has_an_entry_and_every_entry_a_file():
    """The registry lists exactly the languages with a file in web/i18n."""
    files = {path.stem for path in I18N_DIR.glob("*.json")}
    assert set(load_locales()) == files


def test_the_fallback_is_english_left_to_right():
    """The fallback locale is in the registry and is left to right."""
    locale = load_locales()[DEFAULT_LOCALE]
    assert locale.direction == "ltr"
    assert locale.reviewed


def test_optional_tools_can_be_left_out(tmp_path):
    """A locale with no LanguageTool code or Vale styles loads, with nothing to check.

    Args:
        tmp_path (Path): A temporary folder.
    """
    path = tmp_path / "locales.toml"
    path.write_text(GOOD, encoding="utf-8")
    locale = load_locales(path)["en-US"]
    assert locale.languagetool is None
    assert locale.vale == ()


def test_the_wikipedia_language_defaults_to_the_code_s_first_part(tmp_path):
    """Without `wikipedia`, pt-BR uses pt.wikipedia.org; with it, the given code.

    Args:
        tmp_path (Path): A temporary folder.
    """
    path = tmp_path / "locales.toml"
    pt_br = GOOD.replace("locales.en-US", "locales.pt-BR")
    zh = GOOD.replace("locales.en-US", "locales.zh-Hans").replace(
        "reviewed = true", 'reviewed = false\nwikipedia = "zh"'
    )
    path.write_text(GOOD + pt_br + zh, encoding="utf-8")
    locales = load_locales(path)
    assert locales["en-US"].wikipedia == "en"
    assert locales["pt-BR"].wikipedia == "pt"
    assert locales["zh-Hans"].wikipedia == "zh"


@pytest.mark.parametrize(
    "change",
    [
        ('direction = "ltr"', 'direction = "up"'),
        ('scripts = ["latin"]', 'scripts = ["klingon"]'),
        ('scripts = ["latin"]', "scripts = []"),
        ("reviewed = true", 'reviewed = "yes"'),
        ("reviewed = true", 'reviewed = true\nfallback = "pt-BR"'),
        ("reviewed = true", 'reviewed = true\nvale = "UI"'),
        ("reviewed = true", 'reviewed = true\nwikipedia = "PT BR"'),
        ("[locales.en-US]", "[locales.de]"),
    ],
)
def test_bad_values_fail_loudly(tmp_path, change):
    """A wrong, unknown or missing value, or no English entry, is an error.

    Args:
        tmp_path (Path): A temporary folder.
        change (tuple[str, str]): The text replaced in a good registry, and its replacement.
    """
    path = tmp_path / "locales.toml"
    path.write_text(GOOD.replace(*change), encoding="utf-8")
    with pytest.raises(ValueError):
        load_locales(path)


def font_faces() -> dict[tuple[str, str], list[tuple[int, int]]]:
    """The vendored font faces of web/css/tokens.css and the code points each covers.

    Returns:
        dict[tuple[str, str], list[tuple[int, int]]]: (family file name, subset) -> ranges.
    """
    css = (WEB / "css" / "tokens.css").read_text(encoding="utf-8")
    faces: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for family, subset, weight, ranges in FACE.findall(css):
        assert (WEB / "fonts" / f"{family}-{subset}-{weight}-normal.woff2").is_file()
        spans = []
        for item in ranges.split(","):
            low, _, high = item.strip().removeprefix("U+").partition("-")
            spans.append((int(low, 16), int(high or low, 16)))
        faces[family, subset] = spans
    return faces


def ui_font(script: str) -> str:
    """The file name of the UI font that draws a script.

    Args:
        script (str): A registry script, such as "latin" or "cyrillic".

    Returns:
        str: "familjen-grotesk", or the font that stands in for it in that script.
    """
    return UI_FONT.get(script, "familjen-grotesk")


def test_every_script_of_a_locale_has_its_fonts():
    """Each script a locale lists has a UI and a mono face, with its file and a unicode-range."""
    faces = font_faces()
    for code, locale in load_locales().items():
        for script in locale.scripts:
            for family in (ui_font(script), "jetbrains-mono"):
                assert (family, script) in faces, f"{code}: no {family} face for {script}"


@pytest.mark.parametrize("code", sorted(load_locales()))
def test_the_fonts_of_a_locale_s_scripts_cover_its_text(code):
    """Every letter of a UI file is in a unicode-range of the scripts its registry entry lists.

    Args:
        code (str): A locale in the registry.
    """
    faces = font_faces()
    spans = [
        span
        for script in load_locales()[code].scripts
        for span in faces[ui_font(script), script]
    ]
    text = "".join(json.loads((I18N_DIR / f"{code}.json").read_text(encoding="utf-8")).values())
    # Letters and marks only: symbols such as an emoji come from the system's emoji font.
    letters = {char for char in text if unicodedata.category(char)[0] in "LM"}
    missing = {char for char in letters if not any(low <= ord(char) <= high for low, high in spans)}
    assert not missing, f"{code}: letters outside its scripts' fonts: {sorted(missing)}"
