"""Writes docs/HELP*.md and docs/ABOUT*.md from the app's Help and About pages.

The repository and the app say the same: the text comes from the pages' i18n keys
(`web/index.html`, `#help-page` and `#about-page`) in each language of `web/i18n`, and the
pictures from `web/help` (see `scripts/help_media.py`). Run it after changing either page or its
strings; a test fails while the files are out of date.

    uv run python scripts/help_docs.py
"""

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DOCS = ROOT / "docs"
LOCALES = ["en", "pt-BR", "es"]  # English first: it is docs/HELP.md.


class _HelpOutline(HTMLParser):
    """Reads the Help page's structure from index.html as a list of blocks.

    Each block is `(kind, key)`: kind is `title`, `para`, `notice-title`, `notice-text`,
    `section`, `subsection`, `item`, `step` (an item of a numbered list) or `figure` (whose key
    is the picture's name).
    """

    def __init__(self) -> None:
        """Starts outside the Help page."""
        super().__init__()
        self.depth = 0
        self.blocks: list[tuple[str, str]] = []
        self.in_notice = False
        self.in_steps = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Records the i18n key of each element of the Help page.

        Args:
            tag (str): The element's tag.
            attrs (list[tuple[str, str | None]]): Its attributes.
        """
        values = dict(attrs)
        if values.get("id") == "help-page":
            self.depth = 1
            return
        if not self.depth:
            return
        if tag == "section":
            self.depth += 1
        if tag == "div" and "notice" in (values.get("class") or ""):
            self.in_notice = True
        if tag == "ol":
            self.in_steps = True
        key = values.get("data-i18n")
        if tag == "img" and values.get("data-help-img"):
            self.blocks.append(("figure", values["data-help-img"] or ""))
        elif key and tag == "h2":
            self.blocks.append(("title", key))
        elif key and tag == "strong" and self.in_notice:
            self.blocks.append(("notice-title", key))
        elif key and tag == "p":
            self.blocks.append(("notice-text" if self.in_notice else "para", key))
        elif key and tag == "summary":
            self.blocks.append(("section", key))
        elif key and tag == "h3":
            self.blocks.append(("subsection", key))
        elif key and tag == "li":
            self.blocks.append(("step" if self.in_steps else "item", key))

    def handle_endtag(self, tag: str) -> None:
        """Leaves a notice, a numbered list, or the Help page at its closing section.

        Args:
            tag (str): The element's tag.
        """
        if not self.depth:
            return
        if tag == "div":
            self.in_notice = False
        if tag == "ol":
            self.in_steps = False
        if tag == "section":
            self.depth -= 1


def outline() -> list[tuple[str, str]]:
    """The Help page's blocks, in order.

    Returns:
        list[tuple[str, str]]: `(kind, key)` pairs.
    """
    parser = _HelpOutline()
    parser.feed((WEB / "index.html").read_text(encoding="utf-8"))
    return parser.blocks


def doc_path(locale: str, page: str = "HELP") -> Path:
    """Where one language's page is written.

    Args:
        locale (str): The language.
        page (str): `HELP` or `ABOUT`.

    Returns:
        Path: `docs/<page>.md` for English, `docs/<page>.<locale>.md` for the others.
    """
    return DOCS / (f"{page}.md" if locale == "en" else f"{page}.{locale}.md")


def _strings(locale: str) -> dict[str, str]:
    """One language's UI strings, with English for the keys it lacks.

    Args:
        locale (str): The language.

    Returns:
        dict[str, str]: Key -> text.
    """
    english = json.loads((WEB / "i18n" / "en.json").read_text(encoding="utf-8"))
    own = json.loads((WEB / "i18n" / f"{locale}.json").read_text(encoding="utf-8"))
    return {**english, **own}


def _other_languages(locale: str, page: str) -> str:
    """The links to the same page in the other languages.

    Args:
        locale (str): The language of the page being written.
        page (str): `HELP` or `ABOUT`.

    Returns:
        str: The links, separated by dots.
    """
    names = {code: _strings(code)["locale.name"] for code in LOCALES}
    return " · ".join(
        f"[{names[code]}]({doc_path(code, page).name})" for code in LOCALES if code != locale
    )


def _tidy(lines: list[str]) -> str:
    """Joins Markdown lines, with at most one blank line in a row and one final newline.

    Args:
        lines (list[str]): The lines.

    Returns:
        str: The text.
    """
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.rstrip("\n") + "\n"


def render(locale: str) -> str:
    """One language's guide, as Markdown.

    Args:
        locale (str): The language.

    Returns:
        str: The Markdown text.
    """
    strings = _strings(locale)
    others = _other_languages(locale, "HELP")
    lines = [
        "<!-- Generated by scripts/help_docs.py from the app's Help page. Do not edit. -->",
        "",
    ]
    for kind, key in outline():
        if kind == "title":
            lines += [f"# {strings[key]}", "", others, ""]
        elif kind == "para":
            lines += ["", strings[key], ""]
        elif kind == "notice-title":
            lines += [f"> **{strings[key]}**", ">"]
        elif kind == "notice-text":
            lines += [f"> {strings[key]}", ""]
        elif kind == "section":
            lines += ["", f"## {strings[key]}", ""]
        elif kind == "subsection":
            lines += ["", f"### {strings[key]}", ""]
        elif kind == "item":
            lines += [f"- {strings[key]}"]
        elif kind == "step":
            lines += [f"1. {strings[key]}"]
        elif kind == "figure":
            picture = WEB / "help" / locale / f"{key}.webp"
            if not picture.is_file():
                picture = WEB / "help" / "en" / f"{key}.webp"
            caption = strings[f"help.fig.{key}"]
            relative = picture.relative_to(ROOT).as_posix()
            lines += ["", f"![{caption}](../{relative})", "", f"*{caption}*", ""]
    return _tidy(lines)


class _AboutOutline(HTMLParser):
    """Reads the About page from index.html as a list of blocks.

    Each block is `(kind, value)`: kind is `title`, `section` or `para` (whose value is an i18n
    key), `entry` (a list item starts; value `ol` or `ul`), `name` (the entry's literal heading),
    `text` (an i18n key) or `link` (a dict of the link's `href`, `label` and Wikipedia titles).
    """

    def __init__(self) -> None:
        """Starts outside the About page."""
        super().__init__()
        self.depth = 0
        self.blocks: list[tuple[str, object]] = []
        self.lists: list[str] = []
        self.in_item = False
        self.capture: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Records each element of the About page that the Markdown shows.

        Args:
            tag (str): The element's tag.
            attrs (list[tuple[str, str | None]]): Its attributes.
        """
        values = {name: value or "" for name, value in attrs}
        if values.get("id") == "about-page":
            self.depth = 1
            return
        if not self.depth:
            return
        if tag == "section":
            self.depth += 1
        key = values.get("data-i18n")
        if tag in ("ol", "ul"):
            self.lists.append(tag)
        elif tag == "li":
            self.in_item = True
            self.blocks.append(("entry", self.lists[-1]))
        elif tag in ("h4", "a"):
            self.capture = {"tag": tag, "text": "", **values}
        elif key and tag == "h2":
            self.blocks.append(("title", key))
        elif key and tag == "h3":
            self.blocks.append(("section", key))
        elif key and tag == "p":
            self.blocks.append(("text" if self.in_item else "para", key))

    def handle_data(self, data: str) -> None:
        """Collects the text of an entry's heading or of a link.

        Args:
            data (str): The text.
        """
        if self.capture is not None:
            self.capture["text"] += data

    def handle_endtag(self, tag: str) -> None:
        """Closes an entry's heading, a link, an entry, a list, or the About page.

        Args:
            tag (str): The element's tag.
        """
        if not self.depth:
            return
        if self.capture is not None and tag == self.capture["tag"]:
            text = " ".join(self.capture["text"].split())
            if tag == "h4":
                self.blocks.append(("name", text))
            else:
                self.blocks.append(("link", {**self.capture, "label": text}))
            self.capture = None
        elif tag == "li":
            self.in_item = False
        elif tag in ("ol", "ul"):
            self.lists.pop()
        elif tag == "section":
            self.depth -= 1


def _link(link: dict[str, str], locale: str) -> str:
    """One link as Markdown, a Wikipedia one pointing at the article in the page's language.

    Falls back to English, then to the other languages, as the app does.

    Args:
        link (dict[str, str]): The link's `href`, `label` and `data-wiki-<lang>` titles.
        locale (str): The language of the page.

    Returns:
        str: The Markdown link.
    """
    wanted = locale.split("-")[0].lower()
    lang = next((code for code in (wanted, "en", "pt", "es") if link.get(f"data-wiki-{code}")), "")
    if not lang:
        return f"[{link['label']}]({link['href']})"
    path = f"{lang}.wikipedia.org/wiki/{link[f'data-wiki-{lang}'].replace(' ', '_')}"
    return f"[{path}](https://{quote(path, safe='/()_,')})"


def render_about(locale: str) -> str:
    """One language's About page, as Markdown.

    Args:
        locale (str): The language.

    Returns:
        str: The Markdown text.
    """
    strings = _strings(locale)
    parser = _AboutOutline()
    parser.feed((WEB / "index.html").read_text(encoding="utf-8"))
    lines = [
        "<!-- Generated by scripts/help_docs.py from the app's About page. Do not edit. -->",
        "",
    ]
    entries: list[dict] = []
    for kind, value in parser.blocks:
        if kind == "entry":
            entries.append({"list": value, "name": "", "text": "", "links": []})
            continue
        if kind in ("name", "text", "link") and entries and not entries[-1].get("done"):
            entry = entries[-1]
            if kind == "name":
                entry["name"] = value
            elif kind == "text":
                entry["text"] = strings[str(value)]
            else:
                entry["links"].append(_link(value, locale))  # type: ignore[arg-type]
            continue
        for entry in entries:
            if not entry.get("done"):
                lines.append(_entry(entry))
                entry["done"] = True
        if kind == "title":
            lines += [f"# {strings[str(value)]}", "", _other_languages(locale, "ABOUT"), ""]
        elif kind == "section":
            lines += ["", f"## {strings[str(value)]}", ""]
        elif kind == "para":
            lines += ["", strings[str(value)], ""]
    lines += [_entry(entry) for entry in entries if not entry.get("done")]
    return _tidy(lines)


def _entry(entry: dict) -> str:
    """One entry of an About list, as a Markdown list item.

    Args:
        entry (dict): Its `list` (`ol` or `ul`), `name`, `text` and `links`.

    Returns:
        str: The list item.
    """
    marker = "1." if entry["list"] == "ol" else "-"
    links = f" {' · '.join(entry['links'])}" if entry["links"] else ""
    return f"{marker} **{entry['name']}**: {entry['text']}{links}"


def main() -> None:
    """Writes the guide and the About page of every language."""
    for locale in LOCALES:
        for page, text in (("HELP", render(locale)), ("ABOUT", render_about(locale))):
            path = doc_path(locale, page)
            path.write_text(text, encoding="utf-8")
            print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
