"""UI string files (brief §8): every language has the English keys, and nothing it cannot use.

A variant of English (`en-GB`) is the exception: it holds only the strings that differ from `en`,
and the rest falls back to `en`.
"""

import json
import re
from pathlib import Path

import pytest

from app.locales import load_locales

I18N_DIR = Path(__file__).parent.parent.parent / "web" / "i18n"
PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
# The cardinal plural forms (CLDR's, as the browser's Intl.PluralRules names them) of the languages
# whose forms for the counts the app shows are not `one` and `other`. French, Spanish, Italian and
# Portuguese also have `many`, but only for millions, which no count here reaches.
PLURALS = {
    "pl": {"one", "few", "many", "other"},
    "ru": {"one", "few", "many", "other"},
    "uk": {"one", "few", "many", "other"},
    "id": {"other"},
    "vi": {"other"},
    "zh-CN": {"other"},
    "ja": {"other"},
    "ko": {"other"},
}


def load(code: str) -> dict[str, str]:
    """Reads a UI string file.

    Args:
        code (str): The language code.

    Returns:
        dict[str, str]: Key -> string.
    """
    return json.loads((I18N_DIR / f"{code}.json").read_text(encoding="utf-8"))


ENGLISH = load("en-US")
OTHERS = sorted(path.stem for path in I18N_DIR.glob("*.json") if path.stem != "en-US")
ENGLISH_VARIANTS = [code for code in OTHERS if code.split("-")[0] == "en"]
TRANSLATIONS = [code for code in OTHERS if code not in ENGLISH_VARIANTS]


def base_key(key: str) -> str:
    """`saved.count.one` -> `saved.count`; a key without a plural form is its own base.

    Args:
        key (str): A string key.

    Returns:
        str: The key without its plural form.
    """
    head, _, form = key.rpartition(".")
    return head if form in PLURAL_FORMS else key


def english_for(key: str) -> list[str]:
    """The English strings a key translates: itself, or every plural form of its base.

    Args:
        key (str): A key of another language.

    Returns:
        list[str]: The English strings.
    """
    if key in ENGLISH and base_key(key) == key:
        return [ENGLISH[key]]
    base = base_key(key)
    return [ENGLISH[name] for name in ENGLISH if base_key(name) == base]


def test_there_are_other_languages():
    """There are other languages."""
    assert {"pt-BR", "es-419"} <= set(OTHERS)


@pytest.mark.parametrize("code", TRANSLATIONS)
def test_every_english_string_is_translated(code):
    """Every English string is translated.

    Args:
        code (str): A UI language code.
    """
    strings = load(code)
    missing = [
        key for key in ENGLISH if key not in strings and f"{base_key(key)}.other" not in strings
    ]
    assert missing == []


@pytest.mark.parametrize("code", TRANSLATIONS)
def test_plural_keys_have_the_language_s_forms(code):
    """A string with plural forms has every form of its language, and only those.

    Args:
        code (str): A UI language code.
    """
    forms = PLURALS.get(code, {"one", "other"})
    strings = load(code)
    bases = {base_key(key) for key in strings if base_key(key) != key}
    for base in bases:
        have = {key.rpartition(".")[2] for key in strings if base_key(key) == base and key != base}
        assert have == forms, f"{code} {base}: {sorted(have)}, expected {sorted(forms)}"


@pytest.mark.parametrize("code", ENGLISH_VARIANTS)
def test_a_variant_of_english_holds_only_what_differs(code):
    """A variant of English repeats no string of `en`: the rest falls back to it.

    Args:
        code (str): A variant of English, such as `en-GB`.
    """
    same = [key for key, text in load(code).items() if ENGLISH.get(key) == text]
    assert same == []


@pytest.mark.parametrize("code", OTHERS)
def test_no_key_that_english_does_not_have(code):
    """No key that English does not have.

    Args:
        code (str): A UI language code.
    """
    unknown = [key for key in load(code) if not english_for(key)]
    assert unknown == []


@pytest.mark.parametrize("code", OTHERS)
def test_placeholders_match_english(code):
    """Placeholders match English.

    Args:
        code (str): A UI language code.
    """
    for key, text in load(code).items():
        allowed = {name for english in english_for(key) for name in PLACEHOLDER.findall(english)}
        used = set(PLACEHOLDER.findall(text))
        assert used <= allowed, f"{code} {key}: {used - allowed}"


@pytest.mark.parametrize("code", ["en-US", *OTHERS])
def test_each_language_names_itself(code):
    """Each language names itself.

    Args:
        code (str): A UI language code.
    """
    assert load(code)["locale.name"]


def test_locales_endpoint_lists_the_files_english_first(client):
    """Locales endpoint lists the files English first.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    body = client.get("/api/locales").json()
    codes = [item["code"] for item in body["locales"]]
    assert codes[0] == "en-US"
    assert set(codes) == {"en-US", *OTHERS}
    names = {item["code"]: item["name"] for item in body["locales"]}
    assert names["pt-BR"] == "Português (Brasil)"
    assert names["es-419"] == "Español (Latinoamérica)"
    assert names["en-US"] == "English (US)"
    assert body["default"] == "en-US"
    registry = load_locales()
    assert all(item["dir"] == registry[item["code"]].direction for item in body["locales"])
