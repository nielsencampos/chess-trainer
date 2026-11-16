"""What scripts/check_text.py sends to LanguageTool, and which of its matches it lets pass."""

from pathlib import Path

from scripts import check_text

SAMPLE = """# Run it

Start the app with `docker compose up` and open <http://127.0.0.1:8000>.
See [the guide](HOW_TO_INSTALL.md) or [docs/HELP.md](docs/HELP.md) for more.

```bash
uv run pytest
```

| Key | What it does |
|-----|--------------|
| `level` | The bot's strength |

Files such as chess-trainer.zip and snake_case_names are words.
"""


def prose(text: str) -> str:
    """The text LanguageTool reads as prose.

    Args:
        text (str): Markdown.

    Returns:
        str: The prose chunks, joined.
    """
    return "".join(chunk for is_markup, chunk, _ in check_text.split_markup(text) if not is_markup)


def test_markup_is_split_off_and_the_prose_kept():
    """Code, links, tables and file names are markup; the sentences around them are prose."""
    parts = check_text.split_markup(SAMPLE)
    assert "".join(chunk for _, chunk, _ in parts) == SAMPLE
    text = prose(SAMPLE)
    for kept in (
        "Run it",
        "Start the app with",
        "and open",
        "the guide",
        "for more",
        "What it does",
    ):
        assert kept in text, kept
    for dropped in ("docker compose", "uv run pytest", "HOW_TO_INSTALL.md", "chess-trainer.zip"):
        assert dropped not in text, dropped
    assert "snake_case_names" not in text


def test_a_placeholder_reads_as_what_it_stands_for():
    """An i18n string's `{placeholder}` is markup that LanguageTool reads as a word."""
    parts = check_text.split_markup("Left theory at move {move}", {"{move}": "12"})
    assert parts == [(False, "Left theory at move ", ""), (True, "{move}", "12")]


def test_the_language_comes_from_the_file_name():
    """`HELP.zh-CN.md` is Chinese; a name with no known code is English (US)."""
    assert check_text.locale_of(Path("docs/HELP.zh-CN.md")) == "zh-CN"
    assert check_text.locale_of(Path("README.md")) == "en-US"
    assert check_text.locale_of(Path("notes.draft.md")) == "en-US"


def test_a_misspelling_of_a_move_or_a_book_word_is_allowed():
    """A spelling match on SAN or on a word of the book's names passes; others do not."""
    config = {"disabled": {}, "ignore": {}}
    spelling = {"rule": {"id": "MORFOLOGIK_RULE_EN_US", "issueType": "misspelling"}}
    assert check_text.allowed(spelling, "Nxf7+", "en-US", config, set())
    assert check_text.allowed(spelling, "Najdorf", "en-US", config, {"Najdorf"})
    assert not check_text.allowed(spelling, "chesss", "en-US", config, {"Najdorf"})


def test_a_disabled_rule_or_an_ignored_text_is_allowed():
    """A rule disabled for the language, or a text listed for it, passes."""
    config = {
        "disabled": {"pt-BR": ["SOME_RULE"]},
        "ignore": {"pt-BR": [{"text": "lance", "rule": "OTHER_RULE"}]},
    }
    assert check_text.allowed({"rule": {"id": "SOME_RULE"}}, "x", "pt-BR", config, set())
    assert not check_text.allowed({"rule": {"id": "SOME_RULE"}}, "x", "es-419", config, set())
    assert check_text.allowed({"rule": {"id": "OTHER_RULE"}}, "lance", "pt-BR", config, set())
    assert not check_text.allowed({"rule": {"id": "OTHER_RULE"}}, "lances", "pt-BR", config, set())
