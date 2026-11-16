"""Fixes from the 0.7.0 review (#59): review clocks and keys, saved-game dates, stored setup."""

import uuid

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import BASE_URL, VIEWPORT, choose_new_game_mode
from tests.e2e.test_game_flow import ANNOTATED, expect_ply

DATED = """[White "{name}"]
[Black "Bia"]
[Date "2024.01.01"]
[Result "1-0"]

1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0
"""


def import_pgn(page: Page, text: str) -> None:
    """Imports one game by pasting it.

    Args:
        page (Page): The page.
        text (str): The PGN.
    """
    page.locator("#tab-import").click()
    page.locator("#import-text").fill(text)
    page.locator("#import-paste").click()
    expect(page.locator("#import-summary")).to_contain_text("1 imported")


def open_annotated_review(page: Page) -> None:
    """Imports a game with clocks and opens it in the review, at its last move.

    Args:
        page (Page): The page.
    """
    name = f"Clocks{uuid.uuid4().hex}"
    page.goto("/")
    import_pgn(page, ANNOTATED.format(name=name))
    page.locator("#tab-saved").click()
    page.locator(".saved-game", has_text=name).locator(".view-button").click()
    page.locator("#review-bar").wait_for(state="visible")
    expect(page.locator("#top-clock")).to_be_visible()


def test_closing_a_review_hides_its_clocks(page: Page):
    """The review's clocks go away with it, instead of staying on the idle board.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    open_annotated_review(page)
    page.keyboard.press("Escape")
    expect(page.locator("#review-bar")).to_be_hidden()
    expect(page.locator("#top-clock")).to_be_hidden()
    expect(page.locator("#bottom-clock")).to_be_hidden()


def test_arrow_keys_on_a_resizer_do_not_move_the_review(page: Page):
    """An arrow key on a focused bar resizer resizes the bar and leaves the review alone.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    open_annotated_review(page)
    expect_ply(page, 6, 6)
    page.locator("#resize-left").focus()
    page.keyboard.press("ArrowLeft")
    expect_ply(page, 6, 6)


@pytest.fixture
def sao_paulo(browser):
    """A page whose clock is in São Paulo (UTC-3), where midnight UTC is the day before.

    Args:
        browser (Browser): Playwright's browser.

    Yields:
        Page: The page.
    """
    context = browser.new_context(
        base_url=BASE_URL, viewport=VIEWPORT, timezone_id="America/Sao_Paulo", locale="en-US"
    )
    yield context.new_page()
    context.close()


def test_an_imported_game_shows_its_own_date_everywhere(sao_paulo: Page):
    """An imported game's date is the PGN's day in Saved games and in New Game alike.

    Args:
        sao_paulo (Page): A page at UTC-3.
    """
    page = sao_paulo
    name = f"Dated{uuid.uuid4().hex}"
    page.goto("/")
    import_pgn(page, DATED.format(name=name))
    page.locator("#tab-saved").click()
    page.locator("#saved-search").fill(name)  # the players are searched here too
    expect(page.locator(".saved-game", has_text=name)).to_contain_text("1/1/2024")
    page.locator("#tab-new").click()
    choose_new_game_mode(page, "saved")
    page.locator("#from-saved-search").fill(name)
    expect(page.locator("#from-saved-list .saved-game", has_text=name)).to_contain_text("1/1/2024")


def test_a_stored_setup_that_no_longer_exists_falls_back(context):
    """A level, color or pace saved by an older version is replaced by the default.

    Args:
        context (BrowserContext): The browser context.
    """
    page = context.new_page()
    page.add_init_script(
        "localStorage.setItem('chess-trainer.prefs',"
        " JSON.stringify({level: 'gone', color: 'purple', pace: 'slow'}))"
    )
    page.goto("/")
    expect(page.locator("#level")).not_to_have_value("")
    expect(page.locator('input[name="color"][value="white"]')).to_be_checked()
    expect(page.locator('input[name="pace"][value="human"]')).to_be_checked()


def test_clear_keeps_the_opening_tree_open(page: Page):
    """Clear unticks every line and leaves open what was open.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    caro = page.locator('#openings .opening[data-repertoire="caro-kann-defense"]')
    caro.locator("> summary .opening-name").click()
    caro.locator("> summary .opening-check").check()
    page.locator("#clear-selection").click()
    expect(page.locator("#selected-total")).to_have_text("0 selected")
    expect(caro).to_have_attribute("open", "")


def open_in(context, locale: str) -> Page:
    """A page with the UI in a language.

    Args:
        context (BrowserContext): The browser context.
        locale (str): The UI language.

    Returns:
        Page: The page, loaded.
    """
    page = context.new_page()
    page.add_init_script(
        f"localStorage.setItem('chess-trainer.prefs', JSON.stringify({{locale: '{locale}'}}))"
    )
    page.goto("/")
    page.wait_for_function("(code) => document.documentElement.lang === code", arg=locale)
    return page


def test_persian_dates_are_gregorian(context):
    """Persian shows dates in the Gregorian calendar, with Western digits, like every language.

    Args:
        context (BrowserContext): The browser context.
    """
    page = open_in(context, "fa")
    name = f"Dated{uuid.uuid4().hex}"
    import_pgn_quietly(page, DATED.format(name=name))
    page.locator("#tab-saved").click()
    page.locator("#saved-search").fill(name)
    expect(page.locator(".saved-game", has_text=name)).to_contain_text("2024")


def import_pgn_quietly(page: Page, text: str) -> None:
    """Imports one game in any language, waiting for the list instead of the English summary.

    Args:
        page (Page): The page.
        text (str): The PGN.
    """
    page.locator("#tab-import").click()
    page.locator("#import-text").fill(text)
    page.locator("#import-paste").click()
    expect(page.locator("#import-summary")).not_to_be_empty()


def test_the_bot_deviation_chance_is_written_as_the_language_writes_percents(context):
    """Turkish puts the percent sign first; English after the number.

    Args:
        context (BrowserContext): The browser context.
    """
    page = open_in(context, "tr")
    expect(page.locator("#deviate-chance option").first).to_have_text("%20")
    page.locator("#locale-picker").select_option("en-US")
    expect(page.locator("#deviate-chance option").first).to_have_text("20%")


def test_the_new_game_modes_stay_on_one_line_in_german(context):
    """A long mode name ("Gespeicherte Partie") does not wrap to a second line.

    Args:
        context (BrowserContext): The browser context.
    """
    page = open_in(context, "de")
    spans = page.locator("#setup-card .segmented.fit span")
    heights = {round(box["height"]) for box in (spans.nth(i).bounding_box() for i in range(3))}
    assert len(heights) == 1, heights
