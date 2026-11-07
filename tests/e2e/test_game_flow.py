"""Game flows from brief §4, against the real backend and Stockfish."""

import re
import uuid
from pathlib import Path

from playwright.sync_api import Page, expect

from tests.e2e.conftest import (
    BASE_URL,
    choose_new_game_mode,
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
    # The result sits under the moves, the menu is back, and nothing else is offered.
    expect(page.locator(".movebar #end-card")).to_be_visible()
    expect(page.locator("#sidebar-tabs")).to_be_visible()
    expect(page.locator("#sidebar-tabs .tab.active")).to_have_count(0)
    expect(page.locator("#end-card .button")).to_have_text(["Copy PGN", "Download PGN"])


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
    page.locator("#tab-new").click()
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
    page.locator("#tab-new").click()
    play(page)
    wait_for_your_move(page)
    expect(page.locator("#sidebar-tabs")).to_be_hidden()  # no tabs during a game
    resign(page)

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
    page.locator("#tab-import").click()
    expect(page.locator("#saved-card")).to_be_hidden()
    expect(page.locator("#setup-card")).to_be_hidden()

    page.locator("#import-text").fill(good + "\n" + bad)
    page.locator("#import-paste").click()
    expect(page.locator("#import-summary")).to_contain_text("refused")
    expect(page.locator("#import-summary")).to_contain_text("1 refused")
    expect(page.locator("#import-errors li")).to_contain_text("Game 2 (Bad - X): invalid move")
    page.locator("#tab-saved").click()
    expect(page.locator(".saved-game", has_text="Ana - Bia").first).to_contain_text("1-0")
    page.locator("#tab-import").click()

    page.locator("#import-text").fill(good)
    page.locator("#import-paste").click()
    expect(page.locator("#import-summary")).to_have_text("0 imported, 1 already saved, 0 refused.")

    path = tmp_path / "games.pgn"
    path.write_text(unique, encoding="utf-8")
    page.locator("#import-file").set_input_files(str(path))
    expect(page.locator("#import-summary")).to_have_text("1 imported, 0 already saved, 0 refused.")
    page.locator("#tab-saved").click()
    expect(page.locator(".saved-game", has_text=name)).to_have_count(1)


LINE_PGN = """[White "Line{tag}"]
[Black "Test"]
[Date "2026.05.06"]
[Result "1-0"]

1. e4 c6 2. d4 d5 3. e5 1-0
"""


def import_line(page: Page) -> str:
    tag = uuid.uuid4().hex
    page.locator("#tab-import").click()
    page.locator("#import-text").fill(LINE_PGN.format(tag=tag))
    page.locator("#import-paste").click()
    expect(page.locator("#import-summary")).to_contain_text("1 imported")
    return f"Line{tag}"


def choose_saved(page: Page, name: str, ply_label: str | None = None, position=False) -> None:
    choose_new_game_mode(page, "saved")
    expect(page.locator("#setup-card")).to_be_visible()
    expect(page.locator("#openings-field")).to_be_hidden()
    expect(page.locator("#play")).to_be_disabled()
    page.locator("#from-saved-search").fill(name)
    page.locator("#from-saved-list .saved-game input").first.check()
    if ply_label:
        page.locator("#from-saved-ply").select_option(label=ply_label)
    if position:
        page.locator('input[name="from-mode"][value="position"]').check()
    page.locator('input[name="pace"][value="instant"]').check()
    page.locator("#time-control").select_option("none")
    page.locator("#level").select_option("warmup")


def test_train_the_line_of_a_saved_game(page: Page):
    page.goto("/")
    name = import_line(page)
    choose_saved(page, name)
    page.locator('input[name="color"][value="black"]').check()
    play(page)
    wait_for_your_move(page)
    assert moves_text(page) == ["e4"]
    click_move(page, "c7", "c6")
    wait_for_ply(page, 3)
    wait_for_your_move(page)
    assert moves_text(page) == ["e4", "c6", "d4"]
    click_move(page, "e7", "e6")  # the game had 2...d5
    wait_for_ply(page, 5)
    expect(page.locator("#movelist .deviation")).to_have_text("e6")


def test_play_from_the_position_of_a_saved_game(page: Page):
    page.goto("/")
    name = import_line(page)
    choose_saved(page, name, "2... d5", position=True)
    play(page)
    wait_for_your_move(page)
    assert moves_text(page) == ["e4", "c6", "d4", "d5"]
    expect(square(page, "d5")).to_have_attribute("data-piece", "bp")
    click_move(page, "e4", "e5")
    wait_for_ply(page, 6)
    page.reload()
    wait_for_your_move(page)
    assert moves_text(page)[:5] == ["e4", "c6", "d4", "d5", "e5"]


def test_menu_shows_one_screen_at_a_time(page: Page):
    page.goto("/")
    screens = {
        "#tab-new": "#setup-card",
        "#tab-saved": "#saved-card",
        "#tab-import": "#import-card",
        "#tab-openings": "#openings-card",
    }
    for tab, card in screens.items():
        page.locator(tab).click()
        expect(page.locator(tab)).to_have_class(re.compile(r"\bactive\b"))
        for other in screens.values():
            if other == card:
                expect(page.locator(other)).to_be_visible()
            else:
                expect(page.locator(other)).to_be_hidden()
    page.locator("#tab-new").click()
    expect(page.locator("#openings-field")).to_be_visible()
    expect(page.locator("#from-saved")).to_be_hidden()


def open_review(page: Page) -> str:
    name = import_line(page)
    page.locator("#tab-saved").click()
    page.locator("#saved-search").fill("")
    row = page.locator(".saved-game", has_text=name)
    row.locator(".view-button").click()
    page.locator("#review-bar").wait_for(state="visible")
    return name


def test_review_a_saved_game_with_buttons_keys_and_clicks(page: Page):
    page.goto("/")
    name = open_review(page)
    count = page.locator("#review-count")
    expect(count).to_have_text("5 / 5")
    expect(square(page, "e5")).to_have_attribute("data-piece", "wp")
    expect(page.locator("#bottom-name")).to_have_text(name)
    expect(page.locator("#review-next")).to_be_disabled()

    page.locator("#review-prev").click()
    expect(count).to_have_text("4 / 5")
    expect(square(page, "e4")).to_have_attribute("data-piece", "wp")
    page.keyboard.press("ArrowLeft")
    expect(count).to_have_text("3 / 5")
    expect(square(page, "d5")).to_have_attribute("data-piece", "")
    page.keyboard.press("Home")
    expect(count).to_have_text("0 / 5")
    expect(square(page, "e2")).to_have_attribute("data-piece", "wp")
    expect(page.locator("#review-first")).to_be_disabled()
    page.keyboard.press("ArrowRight")
    expect(count).to_have_text("1 / 5")
    page.keyboard.press("End")
    expect(count).to_have_text("5 / 5")
    page.locator("#review-first").click()
    expect(count).to_have_text("0 / 5")
    page.locator("#review-last").click()
    expect(count).to_have_text("5 / 5")

    page.locator('#movelist .move[data-ply="2"]').click()
    expect(count).to_have_text("2 / 5")
    expect(page.locator("#movelist .current")).to_have_text("c6")
    assert page.evaluate("document.querySelectorAll('.square.selected').length") == 0

    page.locator("#review-flip").click()
    expect(page.locator(".square").first).to_have_attribute("data-square", "h1")
    expect(page.locator("#top-name")).to_have_text(name)

    page.keyboard.press("Escape")
    expect(page.locator("#review-bar")).to_be_hidden()
    assert moves_text(page) == []
    expect(page.locator(".square").first).to_have_attribute("data-square", "a8")


def test_pieces_cannot_be_moved_in_a_review(page: Page):
    page.goto("/")
    open_review(page)
    click_move(page, "g1", "f3")
    expect(square(page, "g1")).to_have_attribute("data-piece", "wn")
    expect(page.locator("#review-count")).to_have_text("5 / 5")


def test_play_from_here_goes_to_a_new_game_at_that_move(page: Page):
    page.goto("/")
    open_review(page)
    page.locator('#movelist .move[data-ply="3"]').click()
    expect(page.locator("#review-count")).to_have_text("3 / 5")
    page.locator("#review-play").click()
    expect(page.locator("#review-bar")).to_be_hidden()
    expect(page.locator("#from-saved")).to_be_visible()
    expect(page.locator("#from-saved-ply")).to_have_value("3")
    expect(page.locator('input[name="from-mode"][value="position"]')).to_be_checked()
    page.locator('input[name="pace"][value="instant"]').check()
    page.locator("#time-control").select_option("none")
    page.locator("#level").select_option("warmup")
    play(page)
    wait_for_ply(page, 4)
    assert moves_text(page)[:3] == ["e4", "c6", "d4"]


def test_review_a_book_line_and_start_a_game_after_it(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    page.locator("#tab-openings").click()
    page.locator("#lines-search").fill(ALAPIN)
    line = page.locator("#lines-tree .variant", has_text="Alapin Variation").first
    line.locator(".view-button").click()
    expect(page.locator("#review-count")).to_have_text("3 / 3")
    expect(page.locator("#review-play")).to_be_hidden()
    expect(line.locator("input")).not_to_be_checked()  # the button does not toggle the checkbox
    page.locator("#tab-new").click()
    play(page)
    expect(page.locator("#review-bar")).to_be_hidden()
    wait_for_your_move(page)
    assert moves_text(page) == []


def test_openings_exports_ticked_lines_apart_from_what_new_game_trains(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    expect(page.locator("#selected-total")).to_have_text("1 selected")
    page.locator("#tab-openings").click()
    expect(page.locator("#setup-card")).to_be_hidden()
    expect(page.locator("#lines-total")).to_have_text("0 selected")
    expect(page.locator("#lines-export")).to_be_disabled()
    page.locator("#lines-search").fill(ALAPIN)
    line = page.locator("#lines-tree .variant", has_text="Alapin Variation").first
    line.locator("input").check()
    expect(page.locator("#lines-total")).to_have_text("1 selected")
    with page.expect_download() as download:
        page.locator("#lines-export").click()
    text = Path(download.value.path()).read_text()
    assert ALAPIN in text
    page.locator("#tab-new").click()
    expect(page.locator("#selected-total")).to_have_text("1 selected")
    expect(page.locator("#openings .view-button")).to_have_count(0)


def test_chess960_game_can_be_reviewed_but_not_played(page: Page):
    tag = uuid.uuid4().hex
    fischer = f"""[White "Fischer{tag}"]
[Black "Random"]
[Variant "Chess960"]
[SetUp "1"]
[FEN "nrkbbrqn/pppppppp/8/8/8/8/PPPPPPPP/NRKBBRQN w KQkq - 0 1"]

1. e4 e5 *
"""
    page.goto("/")
    page.locator("#tab-import").click()
    page.locator("#import-text").fill(fischer)
    page.locator("#import-paste").click()
    expect(page.locator("#import-summary")).to_contain_text("1 imported")
    page.locator("#tab-saved").click()
    page.locator(".saved-game", has_text=f"Fischer{tag}").locator(".view-button").click()
    expect(page.locator("#review-count")).to_have_text("2 / 2")
    expect(page.locator("#review-play")).to_be_hidden()
    page.keyboard.press("Home")
    expect(square(page, "a1")).to_have_attribute("data-piece", "wn")
    expect(square(page, "g1")).to_have_attribute("data-piece", "wq")
    page.keyboard.press("Escape")
    choose_new_game_mode(page, "saved")
    page.locator("#from-saved-search").fill(f"Fischer{tag}")
    expect(page.locator("#from-saved-list input").first).to_be_disabled()


def test_leaving_a_finished_game_through_the_menu(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    resign(page)
    expect(square(page, "e4")).to_have_attribute("data-piece", "wp")  # the final position stays
    page.locator("#tab-openings").click()
    expect(page.locator("#end-card")).to_be_hidden()
    expect(page.locator("#openings-card")).to_be_visible()
    expect(square(page, "e2")).to_have_attribute("data-piece", "wp")
    assert moves_text(page) == []
    page.locator("#tab-new").click()
    expect(page.locator("#setup-card")).to_be_visible()
    play(page)
    wait_for_your_move(page)


def test_take_back_a_move_before_the_bot_answers(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none", pace="human", premoves=False)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    button = page.locator("#take-back")
    expect(button).to_be_visible()
    expect(button).to_be_disabled()
    click_move(page, "d2", "d4")  # a deviation; the bot takes 2 to 6 s to answer it
    expect(button).to_be_enabled()
    button.click()
    wait_for_your_move(page)
    expect(square(page, "d2")).to_have_attribute("data-piece", "wp")
    assert moves_text(page) == []
    expect(page.locator("#chips .chip", has_text="In theory")).to_be_visible()
    expect(button).to_be_disabled()
    page.wait_for_timeout(6500)  # the reply that was taken back never shows
    assert moves_text(page) == []
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    assert moves_text(page)[0] == "e4"


def test_take_back_is_not_offered_with_premoves(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none", premoves=True)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    expect(page.locator("#take-back")).to_be_hidden()


def test_review_shows_the_eval_bar_and_book_icons(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    page.locator("#tab-openings").click()
    page.locator("#lines-search").fill(ALAPIN)
    line = page.locator("#lines-tree .variant", has_text="Alapin Variation").first
    line.locator(".view-button").click()
    bar = page.locator("#eval-bar")
    expect(bar).to_be_visible()
    expect(page.locator("#eval-label")).to_have_text(re.compile(r"^(\d+\.\d|M\d+)$"))
    expect(page.locator("#movelist .move-icon-book")).to_have_count(3)
    page.locator("#review-close").click()
    expect(bar).to_be_hidden()


def test_no_eval_bar_during_a_game_and_one_at_the_end(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)
    click_move(page, "d2", "d4")  # leaves the book
    wait_for_ply(page, 4)
    expect(page.locator("#eval-bar")).to_be_hidden()
    expect(page.locator("#movelist .move-icon-book")).to_have_count(2)
    expect(page.locator("#movelist .move-icon-deviation")).to_have_count(1)
    resign(page)
    expect(page.locator("#eval-bar")).to_be_visible()
    expect(page.locator("#eval-label")).not_to_have_text("")
    page.locator("#tab-new").click()
    expect(page.locator("#eval-bar")).to_be_hidden()


def test_eval_bar_follows_fast_moves_without_a_backlog(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    requests: list[str] = []
    page.on(
        "request", lambda r: requests.append(r.url) if r.url.endswith("/api/evaluate") else None
    )
    page.goto("/")
    page.locator("#tab-openings").click()
    page.locator("#lines-search").fill("Najdorf")
    page.locator("#lines-tree .variant .view-button").first.click()
    expect(page.locator("#eval-label")).not_to_have_text("")
    page.wait_for_timeout(1500)
    before = len(requests)
    for _ in range(10):
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(200)
    page.wait_for_timeout(3000)
    # One per second at most, and the last one is the position on screen.
    assert len(requests) - before <= 4
    expect(page.locator("#review-count")).to_have_text(re.compile(r"^\d+ / \d+$"))
