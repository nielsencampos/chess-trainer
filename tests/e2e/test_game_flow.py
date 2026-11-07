"""Game flows from brief §4, against the real backend and Stockfish."""

import re

from playwright.sync_api import Page, expect

from tests.e2e.conftest import (
    BASE_URL,
    click_move,
    drag_move,
    moves_text,
    play,
    square,
    wait_for_ply,
    wait_for_your_move,
)

ALAPIN = "1. e4 c5 2. c3"
CARO_SHORT = "1. e4 c6 2. d4 d5 3. e5 Bf5 4. Nf3"


def resign(page: Page) -> None:
    button = page.locator("#resign")
    button.click()
    expect(button).to_have_text("Click again to resign")
    expect(page.locator("#end-card")).to_be_hidden()
    button.click()
    page.locator("#end-card").wait_for(state="visible")


def test_book_then_engine_then_resign_with_end_card(page: Page, seed_prefs, device):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    expect(page.locator("#chips")).to_contain_text("In theory")

    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    assert moves_text(page) == ["e4", "c5"]
    wait_for_your_move(page)

    drag_move(page, "c2", "c3")
    wait_for_ply(page, 4)  # the Alapin line ends at 2.c3, so this reply came from Stockfish
    wait_for_your_move(page)
    expect(page.locator("#chips")).to_contain_text("Left theory at move 2")
    expect(page.locator("#movelist .move").nth(3)).to_have_class(re.compile(r"\bout\b"))
    expect(page.locator("#movelist .deviation")).to_have_count(0)

    resign(page)
    expect(page.locator("#end-result")).to_have_text("You lost")
    expect(page.locator("#end-termination")).to_have_text("by resignation")
    expect(page.locator("#end-variation")).to_contain_text("B22")
    expect(page.locator("#end-variation")).to_contain_text("Sicilian Defense: Alapin Variation")
    expect(page.locator("#end-theory")).to_have_text("until move 2 (3 of 4 plies)")
    expect(page.locator("#end-deviations")).to_contain_text("No deviations.")
    href = page.locator("#lichess-link").get_attribute("href")
    assert href.startswith("https://lichess.org/analysis/pgn/e4_c5_c3_")
    assert href.endswith("?color=white")


def test_deviation_is_marked_and_listed_with_the_expected_move(page: Page, seed_prefs):
    seed_prefs([CARO_SHORT], color="black", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_ply(page, 1)
    wait_for_your_move(page)
    assert moves_text(page) == ["e4"]

    click_move(page, "c7", "c6")
    wait_for_ply(page, 3)
    wait_for_your_move(page)
    click_move(page, "e7", "e6")  # the book has 2...d5
    wait_for_ply(page, 5)
    wait_for_your_move(page)

    expect(page.locator("#movelist .deviation")).to_have_text("e6")
    expect(page.locator("#chips")).to_contain_text("Left theory at move 2")

    resign(page)
    expect(page.locator("#end-deviations li")).to_have_text("2... e6 — expected d5")
    expect(page.locator("#movelist .deviation")).to_have_text("e6")


def test_unselected_variation_counts_as_a_deviation(page: Page, seed_prefs):
    seed_prefs(["1. e4 c5 2. Nf3 Nc6 3. Bb5"], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)
    click_move(page, "c2", "c3")  # Alapin is in the repertoire but is not selected
    wait_for_ply(page, 4)
    expect(page.locator("#movelist .deviation")).to_have_text("c3")


def test_selected_variation_switch_is_not_a_deviation(page: Page, seed_prefs):
    seed_prefs(["1. e4 c5 2. Nf3 Nc6 3. Bb5", ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)
    click_move(page, "c2", "c3")
    wait_for_ply(page, 4)
    expect(page.locator("#movelist .deviation")).to_have_count(0)


def test_scoresheet_mode_hides_the_list_until_the_end(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none", scoresheet=True)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    expect(page.locator("#movelist")).to_be_hidden()
    expect(page.locator("#scoresheet-note")).to_be_visible()

    click_move(page, "e2", "e4")
    wait_for_your_move(page)
    expect(square(page, "c5")).to_have_attribute("data-piece", "bp")
    expect(page.locator("#movelist")).to_be_hidden()

    resign(page)
    expect(page.locator("#movelist")).to_be_visible()
    wait_for_ply(page, 2)


def test_warning_off_hides_theory_chips_and_marks(page: Page, seed_prefs):
    seed_prefs([CARO_SHORT], color="black", timeControl="none", warning=False)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    expect(page.locator("#chips")).not_to_contain_text("In theory")

    click_move(page, "e7", "e6")  # a deviation, right away
    wait_for_ply(page, 3)
    wait_for_your_move(page)
    expect(page.locator("#chips")).not_to_contain_text("Left theory")
    expect(page.locator("#movelist .deviation")).to_have_count(0)

    resign(page)
    expect(page.locator("#movelist .deviation")).to_have_text("e6")
    expect(page.locator("#chips")).to_contain_text("Left theory at move 1")


def test_human_pace_makes_the_bot_wait(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none", pace="human")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    expect(page.locator("#chips")).to_contain_text("Bot is thinking")
    assert moves_text(page) == ["e4"]  # a book reply takes at least 500 ms at this pace
    wait_for_ply(page, 2)
    wait_for_your_move(page)


def test_auto_play_starts_the_next_game_and_can_be_cancelled(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none", autoplay=True)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)

    resign(page)
    expect(page.locator("#auto-next-text")).to_contain_text("Next game in")
    page.locator("#auto-next-cancel").click()
    expect(page.locator("#auto-next")).to_be_hidden()
    page.wait_for_timeout(1200)
    expect(page.locator("#end-card")).to_be_visible()

    page.locator("#next-game").click()
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)
    resign(page)
    expect(page.locator("#end-card")).to_be_hidden(timeout=8000)  # the countdown ran out
    wait_for_your_move(page)
    assert moves_text(page) == []


def test_copy_pgn(page: Page, context, seed_prefs):
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE_URL)
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)
    resign(page)

    page.locator("#copy-pgn").click()
    expect(page.locator("#copy-pgn")).to_have_text("Copied")
    pgn = page.evaluate("navigator.clipboard.readText()")
    assert '[White "You"]' in pgn
    assert "1. e4 c5" in pgn
    assert pgn.rstrip().endswith("0-1")


def test_nothing_loads_from_outside_the_app(page: Page, seed_prefs):
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    assert requests
    assert [url for url in requests if not url.startswith(BASE_URL)] == []
