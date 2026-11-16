"""Right-to-left languages (#37): the page mirrors, the board never does."""

import json
import re
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import BASE_URL, click_move, play, square, wait_for_your_move
from tests.e2e.test_board import fake_api

RTL = {"ar", "fa", "he"}
YOUR_MOVE = "دورك"  # Arabic: "Your move".


def registry_directions() -> dict[str, str]:
    """Each UI language's direction, as `/api/locales` gives it from the registry.

    Returns:
        dict[str, str]: Code -> `ltr` or `rtl`.
    """
    with urlopen(f"{BASE_URL}/api/locales") as response:
        return {item["code"]: item["dir"] for item in json.load(response)["locales"]}


def test_html_dir_follows_the_registry(page: Page):
    """`<html dir>` is rtl for ar, fa and he and ltr for every other language, back and forth.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    directions = registry_directions()
    assert {code for code, direction in directions.items() if direction == "rtl"} == RTL
    page.goto("/")
    expect(page.locator("html")).to_have_attribute("dir", "ltr")
    for code, direction in directions.items():
        page.locator("#locale-picker").select_option(code)
        expect(page.locator("html")).to_have_attribute("lang", code)
        expect(page.locator("html")).to_have_attribute("dir", direction)


@pytest.mark.parametrize("locale", sorted(RTL))
def test_a_right_to_left_page_keeps_the_board_left_to_right(page: Page, locale: str):
    """The menu moves to the right, while a1 stays bottom-left and h1 bottom-right for White.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        locale (str): A right-to-left locale.
    """
    page.goto("/")
    page.locator("#locale-picker").select_option(locale)
    expect(page.locator("html")).to_have_attribute("dir", "rtl")
    sidebar = page.locator(".sidebar").bounding_box()
    movebar = page.locator(".movebar").bounding_box()
    assert sidebar["x"] > movebar["x"]  # The menu bar sits at the start of the line: the right.
    a1 = square(page, "a1").bounding_box()
    h1 = square(page, "h1").bounding_box()
    a8 = square(page, "a8").bounding_box()
    assert a1["x"] < h1["x"]
    assert a1["y"] > a8["y"]
    # The bottom file letters run A to H from left to right.
    labels = page.locator(".board .coord-file")
    expect(labels).to_have_count(8)
    by_x = sorted((label.bounding_box()["x"], label.inner_text()) for label in labels.all())
    assert [text.lower() for _, text in by_x] == list("abcdefgh")


def test_clicks_and_promotion_land_on_the_right_squares_in_arabic(page: Page, seed_prefs):
    """In Arabic, a click on a square selects that square, and promotion opens on its file.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none", locale="ar")
    fake_api(
        page,
        [("b7b5", "b5"), ("a7a6", "a6"), ("c8b7", "Bb7"), ("b8c6", "Nc6"), ("g7g6", "g6")],
    )
    page.goto("/")
    expect(page.locator("html")).to_have_attribute("dir", "rtl")
    play(page)
    wait_for_your_move(page, YOUR_MOVE)
    # A click at a2's place on screen selects a2: the pointer maps left to right.
    a2 = square(page, "a2")
    box = a2.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    expect(a2).to_have_class(re.compile(r"\bselected\b"))
    a2.click()  # Deselects it again.

    for origin, target in [("a2", "a4"), ("a4", "b5"), ("b5", "a6"), ("a6", "b7")]:
        click_move(page, origin, target)
        wait_for_your_move(page, YOUR_MOVE)
    click_move(page, "b7", "a8")
    picker = page.locator(".board .promotion")
    expect(picker.locator("button")).to_have_count(4)
    target = square(page, "a8").bounding_box()
    shown = picker.bounding_box()
    assert shown["x"] <= target["x"] + target["width"] / 2 <= shown["x"] + shown["width"]
    picker.locator('button[data-promotion="q"]').click()
    expect(square(page, "a8")).to_have_attribute("data-piece", "wq")


@pytest.mark.parametrize(
    ("locale", "tab", "font", "start"),
    [
        ("ar", "ورقة التسجيل", "Noto Sans Arabic", "U+600-6FF"),
        ("fa", "برگه ثبت حرکات", "Noto Sans Arabic", "U+600-6FF"),
        ("he", "טופס רישום", "Noto Sans Hebrew", "U+307-308"),
    ],
)
def test_a_right_to_left_language_loads_its_font(
    page: Page, locale: str, tab: str, font: str, start: str
):
    """Arabic, Persian and Hebrew text use the vendored Noto Sans faces of their script.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        locale (str): The locale.
        tab (str): The Scoresheet menu entry in that language.
        font (str): The vendored font of its script.
        start (str): The start of that face's unicode-range.
    """
    page.goto("/")
    page.locator("#locale-picker").select_option(locale)
    expect(page.locator("#tab-scoresheet")).to_have_text(tab)
    loaded = page.evaluate(
        """async (start) => {
          await document.fonts.ready;
          return [...document.fonts]
            .filter((face) => face.status === "loaded" && face.unicodeRange.startsWith(start))
            .map((face) => face.family);
        }""",
        start,
    )
    assert font in loaded


def test_review_playback_controls_stay_left_to_right_in_arabic(page: Page):
    """First, previous, next and last read left to right in Arabic, like a media player's.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator("#locale-picker").select_option("ar")
    expect(page.locator("html")).to_have_attribute("dir", "rtl")
    page.locator("#tab-openings").click()
    page.locator("#lines-search").fill("1. e4 c5 2. c3")
    page.locator("#lines-tree .variant .view-button").first.click()
    bar = page.locator("#review-bar")
    expect(bar).to_have_attribute("data-ply", "3")
    order = ["review-first", "review-prev", "review-next", "review-last"]
    xs = [page.locator(f"#{name}").bounding_box()["x"] for name in order]
    assert xs == sorted(xs), f"not left to right: {dict(zip(order, xs, strict=True))}"
    # Close and flip mirror with the page: close sits at the far left of the bar.
    close = page.locator("#review-close").bounding_box()["x"]
    assert close < xs[0]
    page.locator("#review-prev").click()
    expect(bar).to_have_attribute("data-ply", "2")
