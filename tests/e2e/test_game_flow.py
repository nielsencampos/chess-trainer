"""Game flows from brief §4, against the real backend and Stockfish."""

import re
import uuid

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


def test_book_then_engine_then_resign_with_end_card(page: Page, seed_prefs):
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


def test_opening_name_follows_the_position_even_outside_the_selection(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    name = page.locator("#opening-name")
    expect(name).to_have_text("—")
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)
    expect(name).to_contain_text("Sicilian Defense")
    click_move(page, "g1", "f3")  # outside the selection, and still a named position
    wait_for_ply(page, 4)
    wait_for_your_move(page)
    expect(name).to_contain_text("Sicilian Defense")
    resign(page)
    expect(name).to_contain_text("Sicilian Defense")
    page.locator("#change-setup").click()
    expect(name).to_have_text("—")
    assert moves_text(page) == []


def test_scoresheet_hides_the_opening_name_until_the_end(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none", scoresheet=True)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_your_move(page)
    expect(square(page, "c5")).to_have_attribute("data-piece", "bp")
    expect(page.locator("#opening-name")).to_have_text("—")
    resign(page)
    expect(page.locator("#opening-name")).to_contain_text("Sicilian Defense")


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


def test_reload_continues_the_game(page: Page, seed_prefs):
    seed_prefs([CARO_SHORT], color="black", timeControl="3i2")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "c7", "c6")
    wait_for_ply(page, 3)
    wait_for_your_move(page)
    click_move(page, "e7", "e6")  # a deviation, which must survive the reload
    wait_for_ply(page, 5)
    wait_for_your_move(page)
    before = moves_text(page)

    page.reload()
    page.locator("#game-card").wait_for(state="visible")
    wait_for_your_move(page)
    expect(page.locator("#setup-card")).to_be_hidden()
    assert moves_text(page) == before
    expect(page.locator("#movelist .deviation")).to_have_text("e6")
    expect(page.locator("#chips")).to_contain_text("Left theory at move 2")
    expect(square(page, "e6")).to_have_attribute("data-piece", "bp")
    expect(page.locator("#opening-name")).not_to_have_text("—")
    assert page.locator(".square").first.get_attribute("data-square") == "h1"
    clock = page.locator("#bottom-clock").text_content()
    assert clock.startswith(("03:", "02:"))

    click_move(page, "g8", "f6")
    wait_for_ply(page, 7)
    wait_for_your_move(page)
    resign(page)
    page.reload()
    expect(page.locator("#setup-card")).to_be_visible()
    expect(page.locator("#game-card")).to_be_hidden()


def test_scoresheet_stays_on_after_a_reload(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none", scoresheet=True)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    page.reload()
    wait_for_your_move(page)
    expect(page.locator("#movelist")).to_be_hidden()
    expect(page.locator("#scoresheet-note")).to_be_visible()


def test_download_pgn(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="3i2")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)
    resign(page)
    with page.expect_download() as download:
        page.locator("#download-pgn").click()
    assert re.fullmatch(r"chess-trainer-\d{4}-\d{2}-\d{2}\.pgn", download.value.suggested_filename)
    with open(download.value.path(), encoding="utf-8") as handle:
        pgn = handle.read()
    assert '[Termination "Normal"]' in pgn
    assert "[%clk" in pgn
    assert "[VariantId " in pgn


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


def finish_quick_game(page: Page) -> None:
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)
    resign(page)


def test_saved_games_tab_lists_filters_and_exports(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    expect(page.locator("#sidebar-tabs")).to_be_visible()
    finish_quick_game(page)
    page.locator("#next-game").click()
    wait_for_your_move(page)
    expect(page.locator("#sidebar-tabs")).to_be_hidden()  # no tabs during a game
    resign(page)
    page.locator("#change-setup").click()

    page.locator("#tab-saved").click()
    expect(page.locator("#setup-card")).to_be_hidden()
    rows = page.locator(".saved-game")
    rows.nth(1).wait_for()
    total = rows.count()
    assert total >= 2
    expect(rows.first).to_contain_text("Lost")
    expect(page.locator("#saved-export")).to_be_disabled()

    page.locator("#saved-result").select_option("win")
    expect(page.locator("#saved-empty")).to_be_visible()
    page.locator("#saved-result").select_option("")
    page.locator("#saved-search").fill("Sicilian")
    expect(rows.first).to_contain_text("Sicilian Defense")
    page.locator("#saved-search").fill("")
    expect(rows).to_have_count(total)

    rows.nth(0).locator("input").check()
    rows.nth(1).locator("input").check()
    expect(page.locator("#saved-export")).to_have_text("Export selected (2)")
    with page.expect_download() as download:
        page.locator("#saved-export").click()
    assert download.value.suggested_filename.endswith("-2-games.pgn")
    with open(download.value.path(), encoding="utf-8") as handle:
        text = handle.read()
    assert text.count("[Event ") == 2

    page.locator("#tab-new").click()
    expect(page.locator("#setup-card")).to_be_visible()
    expect(page.locator("#saved-card")).to_be_hidden()


def test_saved_games_select_all_uses_the_filter(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    finish_quick_game(page)
    page.locator("#change-setup").click()
    page.locator("#tab-saved").click()
    page.locator(".saved-game").first.wait_for()
    page.locator("#saved-search").fill("Sicilian")
    expect(page.locator(".saved-game").first).to_contain_text("Sicilian")
    page.locator("#saved-select-all").check()
    visible = page.locator(".saved-game").count()
    expect(page.locator("#saved-export")).to_have_text(f"Export selected ({visible})")


def test_import_by_text_and_by_file(page: Page, tmp_path):
    good = """[White "Ana"]
[Black "Bia"]
[Date "2026.03.04"]
[Result "1-0"]

1. e4 c6 2. d4 d5 3. e5 1-0
"""
    bad = '[White "Bad"]\n[Black "X"]\n\n1. e4 e4 *\n'
    name = f"File{uuid.uuid4().hex}"
    unique = f'[White "{name}"]\n[Black "Y"]\n\n1. d4 d5 *\n'
    page.goto("/")
    page.locator("#tab-saved").click()
    page.locator("#import-box summary").click()

    page.locator("#import-text").fill(good + "\n" + bad)
    page.locator("#import-paste").click()
    expect(page.locator("#import-summary")).to_contain_text("refused")
    expect(page.locator("#import-summary")).to_contain_text("1 refused")
    expect(page.locator("#import-errors li")).to_contain_text("Game 2 (Bad - X): invalid move")
    expect(page.locator(".saved-game", has_text="Ana - Bia").first).to_contain_text("1-0")

    page.locator("#import-text").fill(good)
    page.locator("#import-paste").click()
    expect(page.locator("#import-summary")).to_have_text("0 imported, 1 already saved, 0 refused.")

    path = tmp_path / "games.pgn"
    path.write_text(unique, encoding="utf-8")
    page.locator("#import-file").set_input_files(str(path))
    expect(page.locator("#import-summary")).to_have_text("1 imported, 0 already saved, 0 refused.")
    expect(page.locator(".saved-game", has_text=name)).to_have_count(1)
