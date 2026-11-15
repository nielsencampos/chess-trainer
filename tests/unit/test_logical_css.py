"""Logical CSS outside the board (#31): the UI mirrors in right-to-left languages, the board never.

Every stylesheet under `web/css/` except `board.css` uses logical inline properties
(`margin-inline-start`, `inset-inline-end`, `text-align: start`...). `board.css` and `board.js`
stay physical on purpose: the board is a fixed left-to-right object.
"""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
PHYSICAL_FILES = {"board.css", "board.js"}
STYLESHEETS = sorted(p for p in (WEB / "css").glob("*.css") if p.name not in PHYSICAL_FILES)
SCRIPTS = sorted(p for p in (WEB / "js").glob("*.js") if p.name not in PHYSICAL_FILES)

# Properties whose name says left or right.
PHYSICAL_NAME = re.compile(
    r"^(?:left|right"
    r"|(?:margin|padding|scroll-margin|scroll-padding)-(?:left|right)"
    r"|border-(?:left|right)(?:-(?:width|style|color))?"
    r"|border-(?:top|bottom)-(?:left|right)-radius)$"
)
# Properties whose value says left or right.
PHYSICAL_VALUE = re.compile(r"^(?:text-align|float|clear|caption-side)$")
# Shorthands whose four values run top, right, bottom, left.
BOX_SHORTHAND = re.compile(
    r"^(?:margin|padding|inset|scroll-margin|scroll-padding|border-(?:width|style|color))$"
)
# Inline styles set from JS: `style.marginLeft`, `style.left`, `setProperty("padding-right"...)`.
JS_PHYSICAL = re.compile(
    r"\.style\.(?:left|right|(?:margin|padding|border|scrollMargin|scrollPadding)(?:Left|Right)\w*"
    r"|border(?:Top|Bottom)(?:Left|Right)Radius)\b"
    r"|\.style\.(?:textAlign|cssFloat)\s*=\s*[\"'`](?:left|right)\b"
    r"|setProperty\(\s*[\"'`](?:left|right|(?:margin|padding|border)-(?:left|right)[\w-]*)[\"'`]"
)


def declarations(css: str) -> list[tuple[int, str, str]]:
    """The declarations of a stylesheet, with comments removed.

    Args:
        css (str): The stylesheet's text.

    Returns:
        list[tuple[int, str, str]]: The line, property and value of each declaration.
    """
    css = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group().count("\n"), css, flags=re.S)
    found = []
    for match in re.finditer(r"([{;]\s*)([a-z-]+)\s*:\s*([^;{}]*)", css):
        line = css.count("\n", 0, match.start(2)) + 1
        found.append((line, match.group(2), " ".join(match.group(3).split())))
    return found


def physical(prop: str, value: str) -> bool:
    """Whether a declaration sets a physical inline direction.

    Args:
        prop (str): The property.
        value (str): Its value.

    Returns:
        bool: True when it names left or right, or sets different left and right sides.
    """
    if PHYSICAL_NAME.match(prop):
        return True
    if PHYSICAL_VALUE.match(prop):
        return re.search(r"\b(?:left|right)\b", value) is not None
    parts = value.split()
    if BOX_SHORTHAND.match(prop):
        return len(parts) == 4 and parts[1] != parts[3]
    if prop == "border-radius":
        corners = value.split("/")
        return any(len(set(side.split())) > 1 for side in corners)
    return False


def test_the_check_finds_physical_properties():
    """The check flags the physical forms and lets the logical ones through."""
    css = """
    a { margin-left: 4px; padding: 1px 2px 3px 4px; /* left: 0; */ text-align: right; }
    b { margin-inline-start: 4px; padding: 1px 2px; text-align: end; border-radius: 4px; }
    c { border-radius: 4px 0 0 4px; right: 0; float: left; padding: 1px 2px 3px 2px; }
    """
    flagged = [prop for _, prop, value in declarations(css) if physical(prop, value)]
    assert flagged == ["margin-left", "padding", "text-align", "border-radius", "right", "float"]
    assert JS_PHYSICAL.search('el.style.marginLeft = "4px"')
    assert JS_PHYSICAL.search("el.style.setProperty('left', x)")
    assert not JS_PHYSICAL.search('el.style.setProperty("--sheet-scale", x)')


@pytest.mark.parametrize("path", STYLESHEETS, ids=lambda path: path.name)
def test_stylesheets_use_logical_inline_properties(path: Path):
    """No physical inline property outside `board.css`, so the UI mirrors in RTL (#37).

    Args:
        path (Path): A stylesheet other than `board.css`.
    """
    found = [
        f"{path.name}:{line}: {prop}: {value}"
        for line, prop, value in declarations(path.read_text())
        if physical(prop, value)
    ]
    assert not found, "use the logical form (margin-inline-start, inset-inline-end...):\n" + (
        "\n".join(found)
    )


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.name)
def test_scripts_set_no_physical_inline_styles(path: Path):
    """No physical inline style set from JS outside `board.js`.

    Args:
        path (Path): A script other than `board.js`.
    """
    found = [
        f"{path.name}:{number}: {text.strip()}"
        for number, text in enumerate(path.read_text().splitlines(), start=1)
        if JS_PHYSICAL.search(text)
    ]
    assert not found, "set the logical property instead:\n" + "\n".join(found)


def test_page_has_no_physical_inline_styles():
    """No physical property in a `style` attribute of the page."""
    found = [
        f"{prop}: {value}"
        for style in re.findall(r'style="([^"]*)"', (WEB / "index.html").read_text())
        for _, prop, value in declarations(";" + style)
        if physical(prop, value)
    ]
    assert not found
