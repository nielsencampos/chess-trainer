"""The locale registry, `i18n/locales.toml` (brief §8): what differs per UI language.

Direction, scripts, LanguageTool code, Vale styles, Wikipedia language and whether the
author reviews it are parameters here, so adding a language is data, not code. The fallback
is always `en`.
"""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LOCALE = "en-US"
REGISTRY_FILE = Path(__file__).parent.parent / "i18n" / "locales.toml"
DIRECTIONS = ("ltr", "rtl")
SCRIPTS = ("latin", "latin-ext", "cyrillic", "devanagari", "cjk", "arabic", "hebrew")
FIELDS = {"direction", "scripts", "languagetool", "vale", "wikipedia", "reviewed"}


@dataclass(frozen=True)
class Locale:
    """One UI language of the registry.

    Attributes:
        code (str): The locale code, as in `web/i18n/{code}.json`.
        direction (str): `ltr` or `rtl`.
        scripts (tuple[str, ...]): The scripts its text needs, from `SCRIPTS`.
        languagetool (str | None): Its LanguageTool code; None skips its texts.
        vale (tuple[str, ...]): The Vale styles for its UI strings; empty skips them.
        reviewed (bool): True when the author reviews it.
        wikipedia (str): Its Wikipedia's language code, for the opening names (`pt` for
            pt.wikipedia.org); by default the code's first part, lowercase.
    """

    code: str
    direction: str
    scripts: tuple[str, ...]
    languagetool: str | None
    vale: tuple[str, ...]
    reviewed: bool
    wikipedia: str


def load_locales(path: Path = REGISTRY_FILE) -> dict[str, Locale]:
    """Reads and checks the registry.

    Args:
        path (Path): The registry file, with a `[locales.<code>]` table per locale.

    Returns:
        dict[str, Locale]: The locales by code, in the file's order.

    Raises:
        ValueError: A table has an unknown or missing field, or a value that is not allowed,
            or `en` is missing.
    """
    with path.open("rb") as handle:
        raw = tomllib.load(handle).get("locales", {})
    locales: dict[str, Locale] = {}
    for code, entry in raw.items():
        where = f"{path}: locales.{code}"
        if unknown := set(entry) - FIELDS:
            raise ValueError(f"{where}: unknown fields {sorted(unknown)}")
        if entry.get("direction") not in DIRECTIONS:
            raise ValueError(f"{where}: direction must be one of {DIRECTIONS}")
        scripts = entry.get("scripts")
        if not scripts or not isinstance(scripts, list) or set(scripts) - set(SCRIPTS):
            raise ValueError(f"{where}: scripts must be a non-empty list from {SCRIPTS}")
        languagetool = entry.get("languagetool")
        if languagetool is not None and (not isinstance(languagetool, str) or not languagetool):
            raise ValueError(f"{where}: languagetool must be a code, or left out")
        vale = entry.get("vale", [])
        if not isinstance(vale, list) or not all(isinstance(s, str) and s for s in vale):
            raise ValueError(f"{where}: vale must be a list of style names, or left out")
        wikipedia = entry.get("wikipedia", code.split("-")[0].lower())
        if not isinstance(wikipedia, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", wikipedia):
            raise ValueError(f"{where}: wikipedia must be a Wikipedia language code, or left out")
        if not isinstance(entry.get("reviewed"), bool):
            raise ValueError(f"{where}: reviewed must be true or false")
        locales[code] = Locale(
            code=code,
            direction=entry["direction"],
            scripts=tuple(scripts),
            languagetool=languagetool,
            vale=tuple(vale),
            reviewed=entry["reviewed"],
            wikipedia=wikipedia,
        )
    if DEFAULT_LOCALE not in locales:
        raise ValueError(f"{path}: the fallback locale {DEFAULT_LOCALE!r} is missing")
    return locales
