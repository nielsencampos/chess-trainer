"""Fills the opening names of a locale: Wikipedia, then the glossary, then machine translation.

`uv run python -m catalog.names <locale>` goes through every family, subgroup and line of
`openings/` and gives it a name in that locale (brief §8):

1. Wikipedia or Wikidata: the English name ("Caro-Kann Defense", or "Family, Subgroup" for a
   subgroup or line) is looked up on the English Wikipedia; the item's article in the locale's
   Wikipedia gives the name, or else its Wikidata label. The page is recorded as `source`.
2. The glossary (`i18n/glossary/{locale}.toml`), segment by segment: the name is split at its
   commas and each segment must be a glossary term, or match a term with a `{name}` placeholder
   ("{name} Variation" → "Variação {name}"), where `{name}` is a proper name kept as it is.
   Recorded as `rule = true`.
3. Machine translation: what is left is listed in `i18n/machine/{locale}.toml` with an empty
   `name`. Once someone fills it in, the next run moves it into `openings/` with `machine = true`.

The names go into the `names` of the opening files, and their origins into
`i18n/names/{locale}.toml`. A name that has a `source`, or any name of a reviewed locale, is
never replaced unless `--overwrite` is given: a run only records where it came from, when
Wikipedia or the glossary give the same name, and lists the ones where Wikipedia differs.
Lookups are cached in `i18n/wikipedia.json`, for every language at once, so a rerun is offline
and gives the same result.
"""

import argparse
import json
import re
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.locales import DEFAULT_LOCALE, Locale, load_locales
from catalog.generate_openings import render
from catalog.translations import (
    GLOSSARY_DIR,
    NAMES_DIR,
    ROOT,
    NameKey,
    NameSource,
    Term,
    load_glossary,
    load_name_sources,
)

OPENINGS_DIR = ROOT / "openings"
MACHINE_DIR = ROOT / "i18n" / "machine"
CACHE_FILE = ROOT / "i18n" / "wikipedia.json"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "chess-trainer-catalog/1.0 (opening names; python-urllib)"
BATCH = 50
SEPARATORS = (", ", ": ", " - ", " \u2013 ")  # The last is an en dash.
# Characters a Wikipedia title cannot have.
NOT_IN_TITLES = re.compile(r"[#<>\[\]|{}]")
DISAMBIGUATION = re.compile(r"\s*\([^()]*\)$")
PLACEHOLDER = "{name}"
# A cache entry: the English article, its Wikidata item, its articles by site and its labels.
CacheEntry = dict | None


class Remote(Protocol):
    """Something that looks English Wikipedia titles up."""

    def fetch(self, titles: list[str]) -> dict[str, CacheEntry]:
        """Looks titles up.

        Args:
            titles (list[str]): English Wikipedia titles.

        Returns:
            dict[str, CacheEntry]: For each title, its entry, or None when it has no article.
        """
        ...


class OfflineError(RuntimeError):
    """A lookup is not in the cache and the run is offline."""


class WikidataRemote:
    """The real lookup: the English Wikipedia for the item, Wikidata for its articles and labels."""

    def __init__(self, pause: float = 0.5) -> None:
        """Creates the lookup.

        Args:
            pause (float): Seconds between requests, to be gentle with the API.
        """
        self.pause = pause

    def _get(self, url: str, params: dict[str, str]) -> dict:
        """Calls a MediaWiki API.

        Args:
            url (str): The API's URL.
            params (dict[str, str]): The query.

        Returns:
            dict: The JSON answer.
        """
        query = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
        request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.load(response)
        time.sleep(self.pause)
        return answer

    def _items(self, titles: list[str]) -> dict[str, tuple[str, str] | None]:
        """Finds the Wikidata item of each title, following redirects.

        A redirect to a section, a disambiguation page or a missing page has no item.

        Args:
            titles (list[str]): Up to `BATCH` English titles.

        Returns:
            dict[str, tuple[str, str] | None]: The article's title and its item, by title.
        """
        query = self._get(
            WIKIPEDIA_API,
            {
                "action": "query",
                "redirects": "1",
                "prop": "pageprops",
                "ppprop": "wikibase_item|disambiguation",
                "titles": "|".join(titles),
            },
        ).get("query", {})
        normalized = {item["from"]: item["to"] for item in query.get("normalized", [])}
        redirects = {item["from"]: item for item in query.get("redirects", [])}
        pages = {page["title"]: page for page in query.get("pages", []) if "title" in page}
        found: dict[str, tuple[str, str] | None] = {}
        for title in titles:
            current, seen = normalized.get(title, title), set()
            while current in redirects and current not in seen:
                seen.add(current)
                if redirects[current].get("tofragment"):
                    current = None
                    break
                current = redirects[current]["to"]
            page = pages.get(current) if current else None
            props = (page or {}).get("pageprops", {})
            if page and "wikibase_item" in props and "disambiguation" not in props:
                found[title] = (page["title"], props["wikibase_item"])
            else:
                found[title] = None
        return found

    def fetch(self, titles: list[str]) -> dict[str, CacheEntry]:
        """Looks titles up, `BATCH` at a time.

        Args:
            titles (list[str]): English Wikipedia titles.

        Returns:
            dict[str, CacheEntry]: For each title, its entry, or None when it has no article.
        """
        entries: dict[str, CacheEntry] = {}
        valid = [title for title in titles if not NOT_IN_TITLES.search(title)]
        entries.update({title: None for title in titles if title not in valid})
        for start in range(0, len(valid), BATCH):
            items = self._items(valid[start : start + BATCH])
            ids = sorted({item[1] for item in items.values() if item})
            entities = {}
            for id_start in range(0, len(ids), BATCH):
                answer = self._get(
                    WIKIDATA_API,
                    {
                        "action": "wbgetentities",
                        "ids": "|".join(ids[id_start : id_start + BATCH]),
                        "props": "sitelinks|labels",
                    },
                )
                entities.update(answer.get("entities", {}))
            for title, item in items.items():
                entity = entities.get(item[1]) if item else None
                if not entity or "missing" in entity:
                    entries[title] = None
                    continue
                entries[title] = {
                    "title": item[0],
                    "item": item[1],
                    "sitelinks": {
                        site: link["title"]
                        for site, link in sorted(entity.get("sitelinks", {}).items())
                        if site.endswith("wiki")
                    },
                    "labels": {
                        language: label["value"]
                        for language, label in sorted(entity.get("labels", {}).items())
                    },
                }
        return entries


class WikipediaCache:
    """The lookups, kept in the repository so a rerun needs no internet."""

    def __init__(self, path: Path, remote: Remote | None) -> None:
        """Reads the cache.

        Args:
            path (Path): The cache file; it need not exist yet.
            remote (Remote | None): Where to look up what the cache lacks; None is offline.
        """
        self.path = path
        self.remote = remote
        self.entries: dict[str, CacheEntry] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )
        self.changed = False

    def prefetch(self, titles: Iterable[str]) -> None:
        """Looks up every title the cache lacks.

        Args:
            titles (Iterable[str]): English Wikipedia titles.

        Raises:
            OfflineError: Some are missing and there is no remote.
        """
        missing = sorted({title for title in titles if title not in self.entries})
        if not missing:
            return
        if self.remote is None:
            raise OfflineError(
                f"{len(missing)} lookups are not in {self.path.name}, e.g. {missing[0]!r}"
            )
        fetched = self.remote.fetch(missing)
        self.entries.update({title: fetched.get(title) for title in missing})
        self.changed = True

    def get(self, title: str) -> CacheEntry:
        """A title's entry.

        Args:
            title (str): An English Wikipedia title, already prefetched.

        Returns:
            CacheEntry: Its entry, or None when it has no article.
        """
        return self.entries.get(title)

    def save(self) -> None:
        """Writes the cache back, sorted, when a lookup added to it."""
        if self.changed:
            text = json.dumps(self.entries, ensure_ascii=False, indent=1, sort_keys=True)
            self.path.write_text(text + "\n", encoding="utf-8")
            self.changed = False


@dataclass(frozen=True)
class Found:
    """A name from Wikipedia or Wikidata.

    Attributes:
        name (str): The name.
        url (str): The page it came from.
    """

    name: str
    url: str


def wiki_name(entry: CacheEntry, locale: Locale, family: str | None = None) -> Found | None:
    """The name an entry gives in a locale: its article's title, or else its Wikidata label.

    A title's "(disambiguation)" ending is dropped. For a subgroup or line, a title that starts
    with the family's localized name and a separator ("Defesa Siciliana, Variante Najdorf")
    keeps only the part after it.

    Args:
        entry (CacheEntry): The lookup's entry.
        locale (Locale): The locale.
        family (str | None): The family's name in the locale, for a subgroup or line.

    Returns:
        Found | None: The name and its page, or None when the item has neither.
    """
    if entry is None:
        return None
    site = locale.wikipedia.replace("-", "_") + "wiki"
    found = None
    if title := entry["sitelinks"].get(site):
        url = f"https://{locale.wikipedia}.wikipedia.org/wiki/{title.replace(' ', '_')}"
        found = Found(DISAMBIGUATION.sub("", title), url)
    else:
        for language in dict.fromkeys((locale.code.lower(), locale.wikipedia)):
            if label := entry["labels"].get(language):
                found = Found(label, f"https://www.wikidata.org/wiki/{entry['item']}")
                break
    if found and family:
        for separator in SEPARATORS:
            prefix = family + separator
            if found.name.casefold().startswith(prefix.casefold()):
                found = Found(found.name[len(prefix) :], found.url)
                break
    return found if found and found.name.strip() else None


class Rules:
    """Builds a name from the glossary, segment by segment."""

    def __init__(self, terms: dict[str, Term]) -> None:
        """Prepares the glossary's terms and templates.

        Args:
            terms (dict[str, Term]): The locale's glossary.
        """
        self.exact: dict[str, str] = {}
        self.templates: list[tuple[re.Pattern[str], str]] = []
        for term in terms.values():
            if PLACEHOLDER in term.term and PLACEHOLDER in term.translation:
                before, _, after = term.term.partition(PLACEHOLDER)
                pattern = re.escape(before) + r"(?P<name>.+?)" + re.escape(after)
                self.templates.append((re.compile(pattern, re.IGNORECASE), term.translation))
            elif PLACEHOLDER not in term.term:
                self.exact[term.term.casefold()] = term.translation
        # The longest fixed text first: "{name} Countergambit" before "{name} Gambit".
        self.templates.sort(key=lambda item: -len(item[0].pattern))
        self.words = {term for term in self.exact if " " not in term}
        self.kept: list[str] = []

    def _is_proper(self, text: str) -> bool:
        """Whether a text reads as a proper name: capitalized words, none of them a term.

        Args:
            text (str): The text `{name}` matched.

        Returns:
            bool: True when it can be kept as it is.
        """
        words = [word for word in re.split(r"[\s-]+", text) if word]
        return bool(words) and all(
            (word[0].isupper() or word[0].isdigit()) and word.casefold() not in self.words
            for word in words
        )

    def segment(self, text: str) -> str | None:
        """Translates one segment.

        Args:
            text (str): A segment of an English name.

        Returns:
            str | None: Its translation, or None when the glossary does not cover it.
        """
        if (exact := self.exact.get(text.casefold())) is not None:
            return exact
        for pattern, translation in self.templates:
            match = pattern.fullmatch(text)
            if match and self._is_proper(match["name"]):
                self.kept.append(match["name"])
                return translation.replace(PLACEHOLDER, match["name"])
        return None

    def translate(self, english: str) -> str | None:
        """Translates a name, every segment or none.

        Args:
            english (str): The English name.

        Returns:
            str | None: The name in the glossary's language, or None. The proper names it kept
                are in `kept` until the next call.
        """
        self.kept = []
        parts = [self.segment(part) for part in english.split(", ")]
        return None if None in parts else ", ".join(parts)


@dataclass
class Item:
    """One name to fill: a family, subgroup or line.

    Attributes:
        key (NameKey): Its kind and key, as in `i18n/names/{locale}.toml`.
        english (str): Its English name.
        query (str): What is looked up on the English Wikipedia.
        family (str): Its family's id.
        names (dict[str, str]): Its `names` object in the opening file, changed in place.
    """

    key: NameKey
    english: str
    query: str
    family: str
    names: dict[str, str]


@dataclass
class Report:
    """What a run did.

    Attributes:
        counts (Counter[str]): Names by outcome: `kept`, `source`, `rule`, `machine`,
            `unrecorded` (a protected name no origin confirms) and `todo` (left for machine
            translation).
        differs (list[str]): Protected names where Wikipedia gives another name.
        proper (Counter[str]): The texts kept as proper names, to spot English words left in.
        todo (int): How many names `i18n/machine/{locale}.toml` lists.
        changed_files (int): How many opening files were written.
    """

    counts: Counter[str] = field(default_factory=Counter)
    differs: list[str] = field(default_factory=list)
    proper: Counter[str] = field(default_factory=Counter)
    todo: int = 0
    changed_files: int = 0


def label(key: NameKey) -> str:
    """A key as it reads in the TOML files.

    Args:
        key (NameKey): A kind and key.

    Returns:
        str: Such as `subgroups.caro-kann-defense."Advance Variation"`.
    """
    kind, parts = key
    if kind == "subgroups":
        return f"{kind}.{parts[0]}.{_quote(parts[1])}"
    return f"{kind}.{parts[0]}"


def _quote(text: str) -> str:
    """A TOML basic string.

    Args:
        text (str): The text.

    Returns:
        str: It quoted; JSON's escapes are TOML's.
    """
    return json.dumps(text, ensure_ascii=False)


def _items(documents: dict[Path, dict]) -> list[Item]:
    """Every family, subgroup and line of the book, families first.

    Args:
        documents (dict[Path, dict]): The opening files' content, by path.

    Returns:
        list[Item]: The names to fill, so each family is named before its subgroups and lines.
    """
    families: list[Item] = []
    others: list[Item] = []
    for document in documents.values():
        family_id, family_en = document["id"], document["names"]["en"]
        families.append(
            Item(("families", (family_id,)), family_en, family_en, family_id, document["names"])
        )
        for variant in document.get("variants", []):
            english = variant["names"]["en"]
            others.append(
                Item(
                    ("subgroups", (family_id, english)),
                    english,
                    f"{family_en}, {english}",
                    family_id,
                    variant["names"],
                )
            )
            others += [_line_item(line, family_id, family_en) for line in variant["lines"]]
        others += [_line_item(line, family_id, family_en) for line in document.get("lines", [])]
    return families + others


def _line_item(line: dict, family_id: str, family_en: str) -> Item:
    """A line's name to fill.

    Args:
        line (dict): The line object.
        family_id (str): Its family's id.
        family_en (str): Its family's English name.

    Returns:
        Item: The name.
    """
    english = line["names"]["en"]
    return Item(
        ("lines", (line["id"],)), english, f"{family_en}, {english}", family_id, line["names"]
    )


def read_machine(path: Path) -> dict[NameKey, tuple[str, str]]:
    """Reads the names left for machine translation.

    Args:
        path (Path): An `i18n/machine/{locale}.toml` file; it need not exist.

    Returns:
        dict[NameKey, tuple[str, str]]: The English name and the translation, empty until
            filled in, by key.
    """
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    entries: dict[NameKey, tuple[str, str]] = {}
    for kind in ("families", "lines"):
        for key, entry in raw.get(kind, {}).items():
            entries[(kind, (key,))] = (entry.get("en", ""), entry.get("name", "").strip())
    for family_id, subgroups in raw.get("subgroups", {}).items():
        for english, entry in subgroups.items():
            entries[("subgroups", (family_id, english))] = (english, entry.get("name", "").strip())
    return entries


def write_machine(path: Path, todo: dict[NameKey, str], locale: str) -> None:
    """Writes the names left for machine translation, or removes the file when there are none.

    Args:
        path (Path): The `i18n/machine/{locale}.toml` file.
        todo (dict[NameKey, str]): The English name by key.
        locale (str): The locale, for the header.
    """
    if not todo:
        path.unlink(missing_ok=True)
        return
    lines = [
        f"# Opening names in {locale} that neither Wikipedia nor the glossary give. Fill in each",
        "# `name` and run `uv run python -m catalog.names " + locale + "` again: filled names move",
        "# into openings/ with `machine = true` and leave this file.",
    ]
    for key, english in todo.items():
        lines += ["", f"[{label(key)}]", f"en = {_quote(english)}", 'name = ""']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_sources(path: Path, sources: dict[NameKey, NameSource], locale: str) -> None:
    """Writes a locale's name sources, in the book's order.

    Args:
        path (Path): The `i18n/names/{locale}.toml` file.
        sources (dict[NameKey, NameSource]): The entries.
        locale (str): The locale, for the header.
    """
    lines = [
        f"# Where each {locale} opening name in openings/ came from (brief §8). Written by",
        f"# `uv run python -m catalog.names {locale}`; a `note` can be added by hand.",
    ]
    for key, source in sources.items():
        lines += ["", f"[{label(key)}]", f"name = {_quote(source.name)}"]
        if source.origin == "source":
            lines.append(f"source = {_quote(source.source or '')}")
        else:
            lines.append(f"{source.origin} = true")
        if source.note:
            lines.append(f"note = {_quote(source.note)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fill_names(
    locale: Locale,
    cache: WikipediaCache,
    *,
    openings_dir: Path = OPENINGS_DIR,
    glossary_dir: Path = GLOSSARY_DIR,
    names_dir: Path = NAMES_DIR,
    machine_dir: Path = MACHINE_DIR,
    overwrite: bool = False,
) -> Report:
    """Fills a locale's opening names and records where each came from.

    Args:
        locale (Locale): The locale; not `en`, which is the source of every name.
        cache (WikipediaCache): The lookups.
        openings_dir (Path): The `openings/` folder.
        glossary_dir (Path): The `i18n/glossary` folder; a locale without a glossary has no
            rule-built names.
        names_dir (Path): The `i18n/names` folder.
        machine_dir (Path): The `i18n/machine` folder.
        overwrite (bool): Replace sourced names and those of a reviewed locale too.

    Returns:
        Report: What was done.

    Raises:
        ValueError: The locale is `en`.
        OfflineError: A lookup is not in the cache and the cache has no remote.
    """
    if locale.code == DEFAULT_LOCALE:
        raise ValueError(f"{DEFAULT_LOCALE} is the source of every name; there is nothing to fill")
    code = locale.code
    paths = sorted(openings_dir.rglob("*.json"))
    documents = {path: json.loads(path.read_text(encoding="utf-8")) for path in paths}
    before = {path: render(document) for path, document in documents.items()}
    glossary = glossary_dir / f"{code}.toml"
    rules = Rules(load_glossary(glossary) if glossary.exists() else {})
    names_path = names_dir / f"{code}.toml"
    old = load_name_sources(names_path) if names_path.exists() else {}
    machine_path = machine_dir / f"{code}.toml"
    filled = read_machine(machine_path)

    items = _items(documents)
    cache.prefetch(item.query for item in items)
    family_items = {
        item.family: cache.get(item.query) for item in items if item.key[0] == "families"
    }
    family_names = {document["id"]: document["names"] for document in documents.values()}
    report = Report()
    sources: dict[NameKey, NameSource] = {}
    todo: dict[NameKey, str] = {}
    for item in items:
        current = item.names.get(code)
        entry = old.get(item.key)
        entry = entry if entry and current is not None and entry.name == current else None
        found = None
        lookup = cache.get(item.query)
        if item.key[0] == "families":
            found = wiki_name(lookup, locale)
        elif lookup and (family_items[item.family] or {}).get("item") != lookup["item"]:
            found = wiki_name(lookup, locale, family_names[item.family].get(code))
        rule = rules.translate(item.english)
        kept = rules.kept
        # Wikipedia's words in the book's title case: the current name, or else the rule's.
        for cased in (current, rule):
            if found and cased and found.name.casefold() == cased.casefold():
                found = Found(cased, found.url)
                break

        protected = current is not None and not overwrite
        protected = protected and (
            locale.reviewed or (entry is not None and entry.origin == "source")
        )
        if protected:
            note = entry.note if entry else None
            if found and found.name == current:
                sources[item.key] = NameSource(current, "source", found.url, note)
                report.counts["kept" if entry and entry.origin == "source" else "source"] += 1
                continue
            if found:
                report.differs.append(
                    f"{label(item.key)}: book {current!r}, Wikipedia {found.name!r} ({found.url})"
                )
            if entry:
                sources[item.key] = entry
                report.counts["kept"] += 1
            elif rule == current:
                sources[item.key] = NameSource(current, "rule", None, note)
                report.counts["rule"] += 1
                report.proper.update(kept)
            else:
                report.counts["unrecorded"] += 1
            continue

        note = entry.note if entry else None
        english, translation = filled.get(item.key, ("", ""))
        if found:
            new = NameSource(
                found.name, "source", found.url, note if current == found.name else None
            )
        elif rule:
            new = NameSource(rule, "rule", None, note if current == rule else None)
            report.proper.update(kept)
        elif translation and english == item.english:
            new = NameSource(translation, "machine")
        elif entry and entry.origin == "machine":
            new = entry
        else:
            todo[item.key] = item.english
            report.counts["todo"] += 1
            continue
        item.names[code] = new.name
        sources[item.key] = new
        report.counts[new.origin] += 1

    for path, document in documents.items():
        text = render(document)
        if text != before[path]:
            path.write_text(text + "\n", encoding="utf-8")
            report.changed_files += 1
    write_sources(names_path, sources, code)
    write_machine(machine_path, todo, code)
    cache.save()
    report.todo = len(todo)
    return report


def main(argv: list[str] | None = None) -> int:
    """Runs the script.

    Args:
        argv (list[str] | None): The arguments; None reads the command line.

    Returns:
        int: The exit code: 0, or 1 when a lookup is missing offline.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("locale", help="a locale of i18n/locales.toml, not en")
    parser.add_argument(
        "--overwrite", action="store_true", help="replace sourced and reviewed names"
    )
    parser.add_argument("--offline", action="store_true", help="use only i18n/wikipedia.json")
    args = parser.parse_args(argv)
    locales = load_locales()
    if args.locale not in locales:
        parser.error(f"{args.locale!r} is not in i18n/locales.toml")
    cache = WikipediaCache(CACHE_FILE, None if args.offline else WikidataRemote())
    try:
        report = fill_names(locales[args.locale], cache, overwrite=args.overwrite)
    except (OfflineError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    counts = ", ".join(f"{name} {count}" for name, count in sorted(report.counts.items()))
    print(f"{args.locale}: {counts}; {report.changed_files} opening files changed")
    if report.todo:
        print(f"{report.todo} names to translate in i18n/machine/{args.locale}.toml")
    for line in report.differs:
        print(f"DIFFERS {line}")
    if report.proper:
        kept = ", ".join(f"{text} ({count})" for text, count in report.proper.most_common())
        print(f"kept as proper names: {kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
