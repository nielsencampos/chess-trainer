"""UI string files (brief §8): every language has the English keys, and nothing it cannot use."""

import json
import re
from pathlib import Path

import pytest

I18N_DIR = Path(__file__).parent.parent.parent / "web" / "i18n"
PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def load(code: str) -> dict[str, str]:
    """Reads a UI string file.

    Args:
        code (str): The language code.

    Returns:
        dict[str, str]: Key -> string.
    """
    return json.loads((I18N_DIR / f"{code}.json").read_text(encoding="utf-8"))


ENGLISH = load("en")
OTHERS = sorted(path.stem for path in I18N_DIR.glob("*.json") if path.stem != "en")


def base_key(key: str) -> str:
    """`saved.count.one` -> `saved.count`; a key without a plural form is its own base.

    Args:
        key (str): A string key.

    Returns:
        str: The key without its plural form.
    """
    head, _, form = key.rpartition(".")
    return head if form in PLURAL_FORMS and key not in ENGLISH else key


def english_for(key: str) -> list[str]:
    """The English strings a key translates: itself, or every plural form of its base.

    Args:
        key (str): A key of another language.

    Returns:
        list[str]: The English strings.
    """
    if key in ENGLISH:
        return [ENGLISH[key]]
    base = base_key(key)
    return [ENGLISH[name] for name in ENGLISH if base_key(name) == base]


def test_there_are_other_languages():
    """There are other languages."""
    assert {"pt-BR", "es"} <= set(OTHERS)


@pytest.mark.parametrize("code", OTHERS)
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


@pytest.mark.parametrize("code", ["en", *OTHERS])
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
    assert codes[0] == "en"
    assert set(codes) == {"en", *OTHERS}
    names = {item["code"]: item["name"] for item in body["locales"]}
    assert names["pt-BR"] == "Português (Brasil)"
    assert names["es"] == "Español"
    assert body["default"] == "en"
