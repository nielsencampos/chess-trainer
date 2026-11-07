"""Setup card, clocks, theme and layout from brief §4 and §4.1."""

import re

from playwright.sync_api import Page, expect

from tests.e2e.conftest import click_move, play, wait_for_your_move

ALAPIN = "1. e4 c5 2. c3"


def family(page: Page, name: str):
    return page.locator(f'.opening[data-repertoire="{name}"]')


def hold_repertoires(page: Page) -> list:
    """Keeps the book request waiting, to test the page before the book has arrived."""
    held: list = []

    def hold(route) -> None:
        held.append(route)

    page.route("**/api/repertoires", hold)
    return held


def wait_until_held(page: Page, held: list) -> None:
    for _ in range(100):
        if held:
            return
        page.wait_for_timeout(50)
    raise AssertionError("the book was never requested")


def test_all_catalog_families_are_listed_and_nothing_starts_selected(page: Page):
    page.goto("/")
    expect(page.locator("#openings .opening")).to_have_count(149)
    expect(page.locator("#selected-total")).to_have_text("0 selected")
    expect(page.locator("#play")).to_be_disabled()
    expect(page.locator("#setup-hint")).to_be_visible()


def test_play_stays_disabled_until_the_book_has_loaded(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    held = hold_repertoires(page)
    page.goto("/")
    expect(page.locator("#play")).to_be_disabled()
    wait_until_held(page, held)
    expect(page.locator("#play")).to_be_disabled()
    held[0].continue_()
    expect(page.locator("#play")).to_be_enabled()


def test_same_openings_for_both_colors_and_board_flips(page: Page):
    page.goto("/")
    expect(page.locator("#openings .opening")).to_have_count(149)
    page.locator('input[name="color"][value="black"]').check()
    expect(page.locator("#openings .opening")).to_have_count(149)
    expect(page.locator(".square").first).to_have_attribute("data-square", "h1")


def test_families_collapse_and_render_lines_when_opened(page: Page):
    page.goto("/")
    caro = family(page, "caro-kann-defense")
    expect(caro.locator(".opening-count")).to_have_text("0/110")
    expect(caro.locator(".variant")).to_have_count(0)
    caro.locator(".opening-name").click()
    expect(caro.locator(".variant")).to_have_count(110)
    expect(caro.locator(".variant-moves").first).to_contain_text("1. e4 c6")


def test_family_checkbox_selection_persists(page: Page):
    page.goto("/")
    caro = family(page, "caro-kann-defense")
    caro.locator(".opening-check").check()
    expect(caro.locator(".opening-count")).to_have_text("110/110")
    expect(page.locator("#selected-total")).to_have_text("110 selected")
    expect(page.locator("#play")).to_be_enabled()

    caro.locator(".opening-name").click()
    caro.locator(".variant input").first.uncheck()
    expect(caro.locator(".opening-count")).to_have_text("109/110")
    assert caro.locator(".opening-check").evaluate("(box) => box.indeterminate")

    page.reload()
    expect(family(page, "caro-kann-defense").locator(".opening-count")).to_have_text("109/110")
    page.locator("#clear-selection").click()
    expect(page.locator("#selected-total")).to_have_text("0 selected")
    expect(page.locator("#play")).to_be_disabled()


def test_search_by_name_eco_and_moves(page: Page):
    page.goto("/")
    search = page.locator("#opening-search")

    search.fill("taimanov")
    sicilian = family(page, "sicilian-defense")
    expect(sicilian.locator(".variant").first).to_be_visible()
    expect(sicilian.locator(".variant-text").first).to_contain_text("Taimanov")

    search.fill("B46")
    expect(sicilian.locator(".variant-eco").first).to_have_text("B46")

    search.fill("1. e4 c5 2. c3")
    expect(sicilian.locator(".variant").first).to_be_visible()
    expect(sicilian.locator(".variant-moves").first).to_contain_text("1. e4 c5 2. c3")

    search.fill("zzzz")
    expect(page.locator("#no-matches")).to_be_visible()
    expect(page.locator("#openings .opening")).to_have_count(0)

    search.fill("")
    expect(page.locator("#openings .opening")).to_have_count(149)


def test_search_typed_before_the_book_loads_still_applies(page: Page):
    held = hold_repertoires(page)
    page.goto("/")
    page.locator("#opening-search").fill("taimanov")
    wait_until_held(page, held)
    held[0].continue_()
    variant = family(page, "sicilian-defense").locator(".variant-text").first
    expect(variant).to_contain_text("Taimanov")
    expect(page.locator("#openings .opening")).not_to_have_count(149)


def test_family_checkbox_during_a_search_only_selects_the_results(page: Page):
    page.goto("/")
    page.locator("#opening-search").fill("B46")
    sicilian = family(page, "sicilian-defense")
    sicilian.locator(".variant").first.wait_for()
    results = sicilian.locator(".variant").count()
    sicilian.locator(".opening-check").check()
    expect(page.locator("#selected-total")).to_have_text(f"{results} selected")


def test_game_from_the_ui_selection(page: Page):
    page.goto("/")
    page.locator("#opening-search").fill(ALAPIN)
    line = page.locator(".variant", has_text="Alapin Variation").first
    line.locator("input").check()
    expect(page.locator("#selected-total")).not_to_have_text("0 selected")
    page.locator('input[name="pace"][value="instant"]').check()
    page.locator("#time-control").select_option("none")
    play(page)
    wait_for_your_move(page)


def test_time_controls_and_levels_are_offered(page: Page):
    page.goto("/")
    expect(page.locator("#time-control option")).to_have_text(
        ["3+2", "10+5", "15+10", "45+30", "No clock"]
    )
    expect(page.locator("#level option")).to_have_text(["Warm-up", "Club", "Strong", "Max"])


def test_clock_runs_adds_increment_turns_red_and_flags(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="3+2")
    page.clock.install()
    page.goto("/")
    play(page)
    wait_for_your_move(page)

    mine = page.locator("#bottom-clock")
    theirs = page.locator("#top-clock")
    expect(mine).to_have_text("03:00")
    expect(mine).to_have_class(re.compile(r"\bactive\b"))
    expect(theirs).not_to_have_class(re.compile(r"\bactive\b"))
    color = "(element) => getComputedStyle(element).backgroundColor"
    accent = mine.evaluate(color)

    page.clock.run_for(10_000)
    expect(mine).to_have_text("02:50")

    click_move(page, "e2", "e4")
    expect(mine).to_contain_text(re.compile(r"02:5[12]"))  # 2 s increment
    wait_for_your_move(page)

    page.clock.run_for(155_000)
    expect(mine).to_have_class(re.compile(r"\blow\b"))
    assert mine.evaluate(color) != accent

    page.clock.run_for(30_000)
    expect(page.locator("#end-result")).to_have_text("You lost")
    expect(page.locator("#end-termination")).to_have_text("on time")


def test_no_clock_hides_the_clocks(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    expect(page.locator("#bottom-clock")).to_be_hidden()
    expect(page.locator("#top-clock")).to_be_hidden()


def background(page: Page) -> str:
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


LIGHT_BG = "rgb(238, 241, 234)"
DARK_BG = "rgb(18, 24, 20)"


def test_theme_follows_the_system_and_can_be_overridden(page: Page):
    page.emulate_media(color_scheme="dark")
    page.goto("/")
    expect(page.locator("#theme-toggle")).to_have_text("Theme: auto")
    assert background(page) == DARK_BG
    page.emulate_media(color_scheme="light")
    assert background(page) == LIGHT_BG

    page.locator("#theme-toggle").click()
    expect(page.locator("#theme-toggle")).to_have_text("Theme: light")
    page.emulate_media(color_scheme="dark")
    assert background(page) == LIGHT_BG

    page.locator("#theme-toggle").click()
    expect(page.locator("#theme-toggle")).to_have_text("Theme: dark")
    page.emulate_media(color_scheme="light")
    assert background(page) == DARK_BG

    page.reload()
    expect(page.locator("#theme-toggle")).to_have_text("Theme: dark")
    assert background(page) == DARK_BG


def test_layout_two_columns_on_desktop_one_on_mobile(page: Page, device):
    page.goto("/")
    page.locator(".square").first.wait_for()
    board = page.locator("#board").bounding_box()
    panel = page.locator(".side-panel").bounding_box()
    assert abs(board["width"] - board["height"]) <= 1
    if device == "desktop":
        assert panel["width"] == 380
        assert panel["x"] > board["x"] + board["width"]
    else:
        assert panel["y"] >= board["y"] + board["height"]
        assert panel["width"] <= 390
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )


def test_layout_switches_at_900_px(page: Page, device):
    if device != "desktop":
        return
    page.goto("/")
    page.locator(".square").first.wait_for()
    columns = "getComputedStyle(document.querySelector('.layout')).gridTemplateColumns"
    page.set_viewport_size({"width": 900, "height": 800})
    assert len(page.evaluate(columns).split()) == 2
    page.set_viewport_size({"width": 899, "height": 800})
    assert len(page.evaluate(columns).split()) == 1


def test_fonts_are_the_vendored_ones(page: Page):
    page.goto("/")
    page.locator(".square").first.wait_for()
    page.evaluate("document.fonts.ready")
    assert page.evaluate("document.fonts.check('16px \"Familjen Grotesk\"')")
    assert page.evaluate("document.fonts.check('16px \"JetBrains Mono\"')")


def test_footer_shows_the_engine_version(page: Page):
    page.goto("/")
    expect(page.locator("#footer-versions")).to_contain_text("chess-trainer 0.1.0")
    expect(page.locator("#footer-versions")).to_contain_text("Stockfish")
