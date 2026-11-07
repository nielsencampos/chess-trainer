"""Setup card, clocks, theme and layout from brief §4 and §4.1."""

import re

from playwright.sync_api import Page, expect

from tests.e2e.conftest import click_move, play, wait_for_your_move

ALAPIN = "sicilian-alapin.main"


def test_openings_follow_the_color_and_variations_collapse(page: Page):
    page.goto("/")
    openings = page.locator("#openings .opening summary > span:not(.opening-count)")
    expect(openings).to_have_text(
        [
            "Sicilian Defense: Alapin",
            "Sicilian Defense: Moscow",
            "Sicilian Defense: Rossolimo",
            "Vienna Game",
        ]
    )
    page.locator('input[name="color"][value="black"]').check()
    expect(openings).to_have_text(["Caro-Kann Defense", "Sicilian Defense: Taimanov"])

    caro = page.locator('.opening[data-repertoire="caro-kann"]')
    expect(caro.locator(".variants")).to_be_hidden()
    caro.locator("summary > span").first.click()
    expect(caro.locator(".variants")).to_be_visible()
    expect(caro.locator(".variant")).to_have_count(17)
    expect(caro.locator(".opening-count")).to_have_text("17/17")


def test_multi_select_and_play_needs_a_selection(page: Page):
    page.goto("/")
    alapin = page.locator('.opening[data-repertoire="sicilian-alapin"]')
    alapin.locator("summary > span").first.click()
    alapin.locator('input[value="sicilian-alapin.stoltz"]').uncheck()
    expect(alapin.locator(".opening-count")).to_have_text("3/4")
    assert alapin.locator(".opening-check").evaluate("(box) => box.indeterminate")

    for repertoire in ("sicilian-alapin", "sicilian-moscow", "sicilian-rossolimo", "vienna"):
        box = page.locator(f'.opening[data-repertoire="{repertoire}"] .opening-check')
        box.check()
        box.uncheck()
    expect(alapin.locator(".opening-count")).to_have_text("0/4")
    expect(page.locator("#play")).to_be_disabled()
    expect(page.locator("#setup-hint")).to_be_visible()

    alapin.locator(f'input[value="{ALAPIN}"]').check()
    expect(page.locator("#play")).to_be_enabled()
    expect(page.locator("#setup-hint")).to_be_hidden()

    page.reload()
    expect(alapin.locator(".opening-count")).to_have_text("1/4")


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
