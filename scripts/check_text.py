"""Checks the prose of the docs and the UI strings with a local LanguageTool server.

Sends `docs/*.md`, `HOW_TO_INSTALL*.md`, `README*.md` and every string of `web/i18n/*.json`
through LanguageTool's HTTP API, each in its own language, and fails on any match that
`scripts/text_check.toml` does not allow. Words of the book's opening names are always allowed,
and so are SAN moves. Markdown code, links' targets, HTML and `{placeholders}` are not checked.

Start the server first (`scripts/languagetool.sh`, which needs Java 17 or newer), then:

    uv run python scripts/check_text.py [--url http://127.0.0.1:8081]
"""

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scripts" / "text_check.toml"
LT_LANG = {"en": "en-US", "pt-BR": "pt-BR", "es": "es"}
# Headings that start another language inside an English README.
README_SECTIONS = {"## Português (Brasil)": "pt-BR", "## Español": "es"}
SAN = re.compile(r"^(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?[!?]*$")
# Markdown that is not prose, by what it stands for in a sentence: a code block (a paragraph
# break), a word (inline code, URLs, a link whose text is a URL, snake_case and file names), a
# table cell
# bar (a paragraph break) or nothing (comments, HTML, link brackets and targets, table rules,
# heading, list and emphasis marks, indentation).
_TARGET = r"\]\((?:[^()\n]|\([^()\n]*\))*\)"
MARKUP = re.compile(
    r"(?P<block>```.*?```)"
    r"|(?P<word>`[^`\n]*`|<https?://[^>\n]+>|https?://[^\s)]+"
    rf"|\[[^\]\s]*[./][^\]\s]*{_TARGET}|\b\w+_\w+\b"
    r"|[\w.…-]+\.(?:exe|zip|dmg|gz|sh|AppImage|json|md)\b)"
    r"|(?P<none><!--.*?-->|<[^>\n]+>|!?\[(?=[^\]\n]*\]\()"
    rf"|{_TARGET}"
    r"|^[ \t]*\|?(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*:?-*:?[ \t]*$"
    r"|^#{1,6} |^[ \t]*(?:[-*]|\d+\.) |^[ \t]+|\*\*?)"
    r"|(?P<cell>\|)",
    re.DOTALL | re.MULTILINE,
)
STANDS_FOR = {"block": "\n\n", "word": "X", "none": "", "cell": "\n\n"}
PLACEHOLDER = re.compile(r"\{\w+\}")
WORD = re.compile(r"[\w'\u2019-]+")  # with straight and curly apostrophes
# Separates the strings of an i18n file sent together, so each is its own paragraph.
I18N_SEP = "\n\n"
# A chunk of text: (is_markup, chunk, what LanguageTool reads in its place).
Part = tuple[bool, str, str]


@dataclass
class Text:
    """A piece of text to check, in one language.

    Attributes:
        where: The file, or the file and the i18n key, for the report.
        lang: The app's locale code (`en`, `pt-BR`, `es`).
        parts: The text as chunks, in order.
        first_line: The file line the text starts on.
        keys: For an i18n file, each string's key and its offset in the text.
    """

    where: str
    lang: str
    parts: list[Part]
    first_line: int = 1
    keys: list[tuple[int, str]] | None = None

    def locate(self, offset: int, whole: str) -> str:
        """Tells where an offset of the text is, for the report.

        Args:
            offset: An offset into the whole text.
            whole: The whole text.

        Returns:
            `file key` for an i18n file, `file:line` otherwise.
        """
        if self.keys is not None:
            return f"{self.where} {max(k for k in self.keys if k[0] <= offset)[1]}"
        return f"{self.where}:{self.first_line + whole.count(chr(10), 0, offset)}"


def split_markup(text: str, stands_for: dict[str, str] | None = None) -> list[Part]:
    """Splits Markdown, or an i18n string, into prose and markup chunks.

    Args:
        text: The text.
        stands_for: For an i18n string, what each `{placeholder}` reads as; None for Markdown.

    Returns:
        The chunks, which join back into the text.
    """
    pattern = MARKUP if stands_for is None else PLACEHOLDER
    parts: list[Part] = []
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append((False, text[last : m.start()], ""))
        if stands_for is None:
            parts.append((True, m.group(), STANDS_FOR[m.lastgroup or "none"]))
        else:
            parts.append((True, m.group(), stands_for.get(m.group(), "X")))
        last = m.end()
    if last < len(text):
        parts.append((False, text[last:], ""))
    return parts


def locale_of(path: Path) -> str:
    """Tells a file's language from its name (`HELP.pt-BR.md` is pt-BR).

    Args:
        path: The file.

    Returns:
        The locale code; English when the name has none.
    """
    suffix = path.name.split(".")[-2] if path.name.count(".") > 1 else "en"
    return suffix if suffix in LT_LANG else "en"


def markdown_texts(path: Path) -> list[Text]:
    """Reads a Markdown file as one text per language section.

    Args:
        path: The file.

    Returns:
        Its texts: one, or one per language section of a README.
    """
    rel = str(path.relative_to(ROOT))
    lang, start, chunk, texts = locale_of(path), 1, [], []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(keepends=True), 1):
        if line.strip() in README_SECTIONS and path.name.startswith("README"):
            texts.append(Text(rel, lang, split_markup("".join(chunk)), start))
            lang, start, chunk = README_SECTIONS[line.strip()], n, []
        chunk.append(line)
    texts.append(Text(rel, lang, split_markup("".join(chunk)), start))
    return texts


def i18n_texts(path: Path) -> list[Text]:
    """Reads a UI string file as one text, each string its own paragraph.

    Args:
        path: A `web/i18n/{locale}.json` file.

    Returns:
        The text, with its placeholders as markup and the offset of each key.
    """
    strings: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    parts: list[Part] = []
    keys: list[tuple[int, str]] = []
    offset = 0
    for key, value in strings.items():
        if key == "locale.name":
            continue
        keys.append((offset, key))
        count = "1" if key.endswith(".one") else "2"
        parts += [*split_markup(value, {"{count}": count}), (False, I18N_SEP, "")]
        offset += len(value) + len(I18N_SEP)
    return [Text(str(path.relative_to(ROOT)), path.stem, parts, keys=keys)]


def book_words() -> set[str]:
    """Collects every word of the book's opening, subgroup and line names, in all languages.

    Returns:
        The words, as written.
    """
    words: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "names" and isinstance(value, dict):
                    for name in value.values():
                        words.update(WORD.findall(name))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in (ROOT / "openings").rglob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return words


def check(url: str, text: Text) -> list[dict]:
    """Sends a text to LanguageTool.

    Args:
        url: The server's base URL.
        text: The text.

    Returns:
        LanguageTool's matches, with offsets into the whole text.

    Raises:
        urllib.error.URLError: The server cannot be reached.
    """
    annotation = [
        {"markup": c, "interpretAs": reads} if is_markup else {"text": c}
        for is_markup, c, reads in text.parts
    ]
    body = urllib.parse.urlencode(
        {"language": LT_LANG[text.lang], "data": json.dumps({"annotation": annotation})}
    ).encode()
    with urllib.request.urlopen(f"{url}/v2/check", body, timeout=120) as response:
        return json.load(response)["matches"]


def allowed(match: dict, flagged: str, lang: str, config: dict, words: set[str]) -> bool:
    """Tells whether a match is allowed by the configuration.

    Args:
        match: A LanguageTool match.
        flagged: The text it flags.
        lang: The text's locale.
        config: `text_check.toml`.
        words: Words allowed in this language (the book's names and the allowlist).

    Returns:
        True when the match is not an error for this project.
    """
    rule = match["rule"]["id"]
    if rule in config["disabled"].get("all", []) or rule in config["disabled"].get(lang, []):
        return True
    if match["rule"].get("issueType") == "misspelling" or "SPELL" in rule or "MORFOLOGIK" in rule:
        tokens = WORD.findall(flagged)
        if tokens and all(t in words or SAN.match(t) for t in tokens):
            return True
    return any(
        flagged == item["text"] and item.get("rule", rule) == rule
        for item in config.get("ignore", {}).get(lang, [])
    )


def export(folder: Path) -> None:
    """Writes the texts Vale cannot read by itself as Markdown files, one per language.

    The UI strings go to `ui.{locale}.md`, one line each, after their key in backticks and with
    their placeholders as code. The
    pt-BR and es sections of the README go to `README.{locale}.md`, on the same line numbers as
    in the README.

    Args:
        folder: Where to write them; it is created if needed.
    """
    folder.mkdir(parents=True, exist_ok=True)
    for path in sorted((ROOT / "web" / "i18n").glob("*.json")):
        strings: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        lines = [
            f"`{key}` {PLACEHOLDER.sub(lambda m: f'`{m.group()}`', value)}\n"
            for key, value in strings.items()
        ]
        (folder / f"ui.{path.stem}.md").write_text("".join(lines), encoding="utf-8")
    for text in markdown_texts(ROOT / "README.md"):
        if text.lang != "en":
            body = "".join(c for _, c, _ in text.parts)
            padded = "\n" * (text.first_line - 1) + body
            (folder / f"README.{text.lang}.md").write_text(padded, encoding="utf-8")


def main() -> int:
    """Checks every text and prints the errors.

    Returns:
        0 when there are none, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_url = os.environ.get("LANGUAGETOOL_URL", "http://127.0.0.1:8081")
    parser.add_argument("--url", default=default_url)
    parser.add_argument("paths", nargs="*", type=Path, help="only these files")
    parser.add_argument("--export", type=Path, help="only write the texts for Vale into a folder")
    args = parser.parse_args()
    if args.export:
        export(args.export)
        return 0

    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    common = book_words() | set(config["allow"]["all"])
    words = {lang: common | set(config["allow"].get(lang, [])) for lang in LT_LANG}
    files = args.paths or sorted(
        {
            *ROOT.glob("docs/*.md"),
            *ROOT.glob("HOW_TO_INSTALL*.md"),
            *ROOT.glob("README*.md"),
            *ROOT.glob("web/i18n/*.json"),
        }
    )
    errors = 0
    for path in files:
        path = path.resolve()
        texts = i18n_texts(path) if path.suffix == ".json" else markdown_texts(path)
        for text in texts:
            whole = "".join(c for _, c, _ in text.parts)
            utf16 = whole.encode("utf-16-le")  # LanguageTool counts offsets in UTF-16 units
            for match in check(args.url, text):
                start, end = 2 * match["offset"], 2 * (match["offset"] + match["length"])
                flagged = utf16[start:end].decode("utf-16-le")
                match["offset"] = len(utf16[:start].decode("utf-16-le"))
                if allowed(match, flagged, text.lang, config, words[text.lang]):
                    continue
                errors += 1
                where = text.locate(match["offset"], whole)
                fixes = ", ".join(r["value"] for r in match["replacements"][:3])
                rule = match["rule"]["id"]
                print(f"{where}: [{text.lang}] {rule} '{flagged}': {match['message']}")
                if fixes:
                    print(f"    suggestion: {fixes}")
    print(f"{errors} error(s)" if errors else "No text errors.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
