"""Setup card, clocks, theme and layout from brief §4 and §4.1."""

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import click_move, play, wait_for_your_move

ALAPIN = "1. e4 c5 2. c3"


def family(page: Page, name: str):
    """An opening family in the setup tree.

    Args:
        page (Page): The page.
        name (str): The family id.

    Returns:
        Locator: The family's element.
    """
    return page.locator(f'#openings .opening[data-repertoire="{name}"]')


def hold_repertoires(page: Page) -> list:
    """Keeps the book request waiting, to test the page before the book has arrived.

    Args:
        page (Page): The page.

    Returns:
        list: The held requests, to fulfill later.
    """
    held: list = []

    def hold(route) -> None:
        """Holds a book request.

        Args:
            route (Route): The intercepted request.
        """
        held.append(route)

    page.route("**/api/repertoires", hold)
    return held


def wait_until_held(page: Page, held: list) -> None:
    """Waits until the book request is held.

    Args:
        page (Page): The page.
        held (list): The list from `hold_repertoires`.

    Raises:
        AssertionError: The book was not requested within 5 s.
    """
    for _ in range(100):
        if held:
            return
        page.wait_for_timeout(50)
    raise AssertionError("the book was never requested")


def test_all_catalog_families_are_listed_and_nothing_starts_selected(page: Page):
    """All catalog families are listed and nothing starts selected.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    expect(page.locator("#openings .opening")).to_have_count(122)
    expect(page.locator("#selected-total")).to_have_text("0 selected")
    expect(page.locator("#play")).to_be_disabled()
    expect(page.locator("#setup-hint")).to_be_visible()


def test_play_stays_disabled_until_the_book_has_loaded(page: Page, seed_prefs):
    """Play stays disabled until the book has loaded.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], color="white", timeControl="none")
    held = hold_repertoires(page)
    page.goto("/")
    expect(page.locator("#play")).to_be_disabled()
    wait_until_held(page, held)
    expect(page.locator("#play")).to_be_disabled()
    held[0].continue_()
    expect(page.locator("#play")).to_be_enabled()


def test_same_openings_for_both_colors_and_board_flips(page: Page):
    """Same openings for both colors and board flips.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    expect(page.locator("#openings .opening")).to_have_count(122)
    page.locator('input[name="color"][value="black"]').check()
    expect(page.locator("#openings .opening")).to_have_count(122)
    expect(page.locator(".square").first).to_have_attribute("data-square", "h1")


def test_tree_of_groups_openings_subgroups_and_lines(page: Page):
    """Tree of groups openings subgroups and lines.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    groups = page.locator("#openings .tree-group > summary .opening-name")
    expect(groups).to_have_text(
        ["King's Pawn (1.e4)", "Queen's Pawn (1.d4)", "Flank (1.c4, 1.Nf3 ...)", "Others"]
    )
    first = page.locator(
        '#openings [data-group="kings-pawn"] .opening > summary .opening-name'
    ).first
    expect(first).to_have_text("Sicilian Defense")
    others = page.locator('#openings [data-group="kings-pawn"] > .tree-children > .tree-others')
    expect(others).to_have_count(1)

    caro = family(page, "caro-kann-defense")
    expect(caro.locator("> summary .opening-count")).to_have_text("0/110")
    expect(caro.locator(".variant")).to_have_count(0)  # built when first opened
    caro.locator("> summary .opening-name").click()
    expect(caro.locator(".variant")).to_have_count(110)
    advance = caro.locator(".tree-variant", has_text="Advance Variation").first
    advance.locator("> summary .opening-name").click()
    expect(advance.locator(".variant-moves").first).to_contain_text("1. e4 c6 2. d4 d5 3. e5")
    loose = caro.locator(".tree-variant", has=page.locator("> summary", has_text="Others"))
    expect(loose).to_have_count(1)


def test_checking_a_group_selects_everything_inside(page: Page):
    """Checking a group selects everything inside.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    group = page.locator('#openings [data-group="flank"]')
    group.locator("> summary .tree-check").check()
    count = group.locator("> summary .opening-count").text_content().split("/")[0]
    assert int(count) > 100
    expect(page.locator("#selected-total")).to_have_text(f"{count} selected")
    english = family(page, "english-opening")
    expect(english.locator("> summary .opening-check")).to_be_checked()
    group.locator("> summary .tree-check").uncheck()
    expect(page.locator("#selected-total")).to_have_text("0 selected")


def test_family_checkbox_selection_persists(page: Page):
    """Family checkbox selection persists.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    caro = family(page, "caro-kann-defense")
    caro.locator(".opening-check").check()
    expect(caro.locator("> summary .opening-count")).to_have_text("110/110")
    expect(page.locator("#selected-total")).to_have_text("110 selected")
    expect(page.locator("#play")).to_be_enabled()

    caro.locator("> summary .opening-name").click()
    first_sub = caro.locator(".tree-variant").first
    first_sub.locator("> summary .opening-name").click()
    first_sub.locator(".variant input").first.uncheck()
    expect(caro.locator("> summary .opening-count")).to_have_text("109/110")
    assert caro.locator("> summary .opening-check").evaluate("(box) => box.indeterminate")

    page.reload()
    caro = family(page, "caro-kann-defense")
    expect(caro.locator("> summary .opening-count")).to_have_text("109/110")
    page.locator("#clear-selection").click()
    expect(page.locator("#selected-total")).to_have_text("0 selected")
    expect(page.locator("#play")).to_be_disabled()


def test_search_by_name_eco_and_moves(page: Page):
    """Search by name ECO and moves.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
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
    expect(page.locator("#openings .opening")).to_have_count(122)


def test_search_typed_before_the_book_loads_still_applies(page: Page):
    """Search typed before the book loads still applies.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    held = hold_repertoires(page)
    page.goto("/")
    page.locator("#opening-search").fill("taimanov")
    wait_until_held(page, held)
    held[0].continue_()
    variant = family(page, "sicilian-defense").locator(".variant-text").first
    expect(variant).to_contain_text("Taimanov")
    expect(page.locator("#openings .opening")).not_to_have_count(122)


def test_select_all_respects_the_search(page: Page):
    """Select all respects the search.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    expect(page.locator("#openings .opening").first).to_be_visible()
    page.locator("#select-all").click()
    expect(page.locator("#selected-total")).to_have_text("3865 selected")
    expect(page.locator('#openings [data-group="flank"] > summary .tree-check')).to_be_checked()
    expect(page.locator("#play")).to_be_enabled()
    page.locator("#clear-selection").click()
    expect(page.locator("#selected-total")).to_have_text("0 selected")

    page.locator("#opening-search").fill("B46")
    family(page, "sicilian-defense").locator(".variant").first.wait_for()
    results = page.locator(".variant").count()
    page.locator("#select-all").click()
    expect(page.locator("#selected-total")).to_have_text(f"{results} selected")


def test_family_checkbox_during_a_search_only_selects_the_results(page: Page):
    """Family checkbox during a search only selects the results.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator("#opening-search").fill("B46")
    sicilian = family(page, "sicilian-defense")
    sicilian.locator(".variant").first.wait_for()
    results = sicilian.locator(".variant").count()
    sicilian.locator("> summary .opening-check").check()
    expect(page.locator("#selected-total")).to_have_text(f"{results} selected")


def test_game_from_the_ui_selection(page: Page):
    """Game from the UI selection.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
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
    """Time controls and levels are offered.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    groups = page.locator("#time-control optgroup")
    expect(groups).to_have_count(4)
    assert [g.get_attribute("label") for g in groups.all()] == [
        "Bullet",
        "Blitz",
        "Rapid",
        "Classical",
    ]
    expect(page.locator("#time-control option")).to_have_text(
        [
            "30 s",
            "1 min",
            "2 min",
            "5 min",
            "10 min",
            "3 min, +2 s",
            "5 min, 2 s US delay",
            "25 min",
            "25 min, +10 s",
            "25 min, 10 s delay",
            "25 min, 5 s US delay",
            "60 min",
            "120 min",
            "120 + 30 min",
            "120 + 60 min",
            "120 + 60 + 30 min",
            "120 + 60 + 60 min",
            "90 min, +30 s",
            "90 + 30 min, +30 s",
            "100 + 50 + 15 min, +30 s",
            "115 min, 5 s delay",
            "120 + 15 min, 30 s delay",
            "120 + 60 + 15 min, 30 s delay",
            "115 + 60 min, 5 s US delay",
            "No clock",
        ]
    )
    expect(page.locator("#level option")).to_have_text(
        ["Warm-up (800-)", "Club (1320)", "Strong (1900)", "Master (2600)", "Max (3500+)"]
    )


def test_bot_deviation_option_shows_its_choices(page: Page):
    """The bot deviation option shows its two choices while on, and is hidden for Chess960.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    expect(page.locator("#deviate-options")).to_be_hidden()
    page.locator("#opt-deviate").check()
    expect(page.locator("#deviate-options")).to_be_visible()
    expect(page.locator("#deviate-from option")).to_have_text(["3", "4", "5", "6", "7"])
    expect(page.locator("#deviate-chance option")).to_have_text(
        ["20%", "30%", "40%", "50%", "60%", "70%"]
    )
    expect(page.locator("#deviate-from")).to_have_value("3")
    expect(page.locator("#deviate-chance")).to_have_value("30")
    page.locator('input[name="new-mode"][value="chess960"]').check(force=True)
    expect(page.locator("#deviate-toggle")).to_be_hidden()
    expect(page.locator("#deviate-options")).to_be_hidden()


def test_a_removed_saved_time_control_falls_back_to_the_default(page: Page, seed_prefs):
    """A removed saved time control falls back to the default.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], timeControl="45+30")
    page.goto("/")
    expect(page.locator("#time-control")).to_have_value("25i10")


def test_an_old_scoresheet_preference_is_ignored(page: Page, seed_prefs):
    """An old scoresheet preference is ignored.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], color="white", timeControl="none", scoresheet=True)
    page.goto("/")
    expect(page.locator("#show-moves")).to_be_checked()
    play(page)
    wait_for_your_move(page)
    # The list is empty, so check the attribute.
    expect(page.locator("#movelist")).to_have_js_property("hidden", False)
    expect(page.locator("#opening-name")).to_be_visible()


def test_clock_periods_delays_and_hours(page: Page, seed_prefs):
    """Clock periods delays and hours.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], color="white", timeControl="90+30i30")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    expect(page.locator("#bottom-clock")).to_have_text("1:30:00")
    remaining = page.evaluate(
        """async () => {
          const { Clocks } = await import("/js/clock.js");
          let now = 0;
          performance.now = () => now;
          const make = (control) => {
            const clocks = new Clocks(() => {}, () => {});
            clocks.reset({ base_ms: 100000, increment_ms: 0, periods: [], delay_ms: 0,
                           delay_kind: null, ...control });
            return clocks;
          };
          const turn = (clocks, ms) => {
            clocks.start("w");
            now += ms;
            clocks.press("w");
            return clocks.remaining.w;
          };

          const three = make({ periods: [{ after_moves: 40, add_ms: 5000 },
                                         { after_moves: 60, add_ms: 7000 }] });
          const seen = [];
          for (let move = 1; move <= 61; move += 1) {
            three.press("w");
            seen.push(three.remaining.w);
          }

          const bronstein = make({ delay_ms: 10000, delay_kind: "bronstein" });
          const us = make({ delay_ms: 10000, delay_kind: "us" });
          const increment = make({ increment_ms: 2000 });
          return {
            at39: seen[38], at40: seen[39], at41: seen[40], at59: seen[58], at60: seen[59],
            black: three.remaining.b,
            bronstein: [turn(bronstein, 3000), turn(bronstein, 15000)],
            us: [turn(us, 3000), turn(us, 15000)],
            increment: turn(increment, 3000),
          };
        }"""
    )
    assert remaining["at39"] == 100_000
    assert remaining["at40"] == 105_000
    assert remaining["at41"] == 105_000
    assert remaining["at59"] == 105_000
    assert remaining["at60"] == 112_000
    assert remaining["black"] == 100_000
    assert remaining["bronstein"] == [100_000, 95_000]  # used time back, up to the delay
    assert remaining["us"] == [100_000, 95_000]  # the clock waits for the delay
    assert remaining["increment"] == 99_000


def test_clock_runs_adds_increment_turns_red_and_flags(page: Page, seed_prefs):
    """Clock runs adds increment turns red and flags.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], color="white", timeControl="3i2")
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
    """No clock hides the clocks.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    expect(page.locator("#bottom-clock")).to_be_hidden()
    expect(page.locator("#top-clock")).to_be_hidden()


def background(page: Page) -> str:
    """The page's background color.

    Args:
        page (Page): The page.

    Returns:
        str: The computed color, such as `rgb(31, 26, 23)`.
    """
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


LIGHT_BG = "rgb(236, 235, 232)"
DARK_BG = "rgb(31, 26, 23)"


def test_theme_follows_the_system_and_can_be_overridden(page: Page):
    """Theme follows the system and can be overridden.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
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


def test_sidebar_on_the_left_and_the_board_filling_the_rest(page: Page):
    """Sidebar on the left and the board filling the rest.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator(".square").first.wait_for()
    board = page.locator("#board").bounding_box()
    sidebar = page.locator(".sidebar").bounding_box()
    assert abs(board["width"] - board["height"]) <= 1
    assert (sidebar["x"], sidebar["y"], sidebar["width"]) == (0, 0, 380)
    assert sidebar["height"] == 720
    assert board["x"] >= sidebar["width"]
    # The page itself never scrolls: the sidebar does.
    assert page.evaluate(
        "document.documentElement.scrollHeight <= document.documentElement.clientHeight"
    )
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    assert page.locator(".sidebar").evaluate("(el) => el.scrollHeight > el.clientHeight")


def test_move_bar_on_the_right(page: Page):
    """Move bar on the right.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator(".square").first.wait_for()
    board = page.locator("#board").bounding_box()
    bar = page.locator(".movebar").bounding_box()
    assert bar["x"] >= board["x"] + board["width"]
    assert bar["x"] + bar["width"] == 1280
    assert (bar["y"], bar["height"]) == (0, 720)
    expect(page.locator("#opening-name")).to_have_text("—")
    expect(page.locator("#chips .chip")).to_have_count(0)  # no game yet


def width_of(page: Page, selector: str) -> float:
    """The width of an element.

    Args:
        page (Page): The page.
        selector (str): The element's selector.

    Returns:
        float: Its width in pixels.
    """
    return page.locator(selector).bounding_box()["width"]


def drag_handle(page: Page, handle: str, to_x: float) -> None:
    """Drags a bar's resize handle to a horizontal position.

    Args:
        page (Page): The page.
        handle (str): The handle's selector.
        to_x (float): Where to drop it.
    """
    box = page.locator(handle).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, 300)
    page.mouse.down()
    page.mouse.move(to_x, 300, steps=5)
    page.mouse.up()


def test_dragging_resizes_the_bars(page: Page):
    """Dragging resizes the bars.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto("/")
    page.locator(".square").first.wait_for()

    drag_handle(page, "#resize-left", 500)
    assert abs(width_of(page, ".sidebar") - 500) <= 1

    drag_handle(page, "#resize-right", 1920 - 400)
    assert abs(width_of(page, ".movebar") - 400) <= 1

    page.reload()
    page.locator(".square").first.wait_for()
    assert abs(width_of(page, ".sidebar") - 500) <= 1
    assert abs(width_of(page, ".movebar") - 400) <= 1

    page.locator("#resize-left").dblclick()
    assert abs(width_of(page, ".sidebar") - 380) <= 1


def test_bar_widths_have_limits_and_keep_room_for_the_board(page: Page):
    """Bar widths have limits and keep room for the board.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator(".square").first.wait_for()
    drag_handle(page, "#resize-left", 50)
    assert abs(width_of(page, ".sidebar") - 350) <= 1
    drag_handle(page, "#resize-right", 1280 - 50)
    assert abs(width_of(page, ".movebar") - 350) <= 1
    drag_handle(page, "#resize-left", 1200)
    board = page.locator("#board").bounding_box()
    assert board["width"] >= 320
    assert board["x"] + board["width"] <= page.locator(".movebar").bounding_box()["x"]


def test_arrow_keys_resize_a_bar(page: Page):
    """Arrow keys resize a bar.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator(".square").first.wait_for()
    page.locator("#resize-left").focus()
    page.keyboard.press("ArrowRight")
    assert abs(width_of(page, ".sidebar") - 400) <= 1
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    assert abs(width_of(page, ".sidebar") - 360) <= 1


def test_bars_hide_and_show_and_the_board_uses_the_space(page: Page):
    """Bars hide and show and the board uses the space.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.set_viewport_size({"width": 1920, "height": 700})
    page.goto("/")
    page.locator(".square").first.wait_for()
    page.set_viewport_size({"width": 1280, "height": 1000})
    with_bars = width_of(page, "#board")

    page.locator("#toggle-left").click()
    expect(page.locator(".sidebar")).to_be_hidden()
    expect(page.locator("#toggle-left")).to_be_visible()
    expect(page.locator("#toggle-left")).to_have_attribute("aria-label", "Show the left bar")
    page.locator("#toggle-right").click()
    expect(page.locator(".movebar")).to_be_hidden()
    expect(page.locator("#toggle-right")).to_be_visible()
    assert width_of(page, "#board") > with_bars

    page.reload()
    page.locator(".square").first.wait_for()
    expect(page.locator(".sidebar")).to_be_hidden()
    expect(page.locator(".movebar")).to_be_hidden()

    page.locator("#toggle-left").click()
    page.locator("#toggle-right").click()
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.locator(".movebar")).to_be_visible()
    expect(page.locator("#toggle-left")).to_have_attribute("aria-label", "Hide the left bar")
    assert abs(width_of(page, "#board") - with_bars) <= 1


@pytest.mark.parametrize(
    ("toggle", "gone"), [("#toggle-left", ".sidebar"), ("#toggle-right", ".movebar")]
)
def test_hiding_one_bar_keeps_the_rest_in_place(page: Page, toggle, gone):
    """Hiding one bar keeps the rest in place.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        toggle (str): The selector of the bar's hide button.
        gone (str): The selector of the bar it hides.
    """
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.goto("/")
    page.locator(".square").first.wait_for()
    kept = ".movebar" if gone == ".sidebar" else ".sidebar"
    kept_before = page.locator(kept).bounding_box()
    page.locator(toggle).click()
    expect(page.locator(gone)).to_be_hidden()

    assert page.locator(kept).bounding_box() == kept_before
    area = page.locator(".board-area").bounding_box()
    board = page.locator("#board").bounding_box()
    assert area["width"] > 1000
    assert board["x"] >= area["x"]
    assert board["x"] + board["width"] <= area["x"] + area["width"]
    assert board["y"] + board["height"] <= 1080
    # Centered in what is left, and everything still fits with no page scroll.
    middle = board["x"] + board["width"] / 2
    assert abs(middle - (area["x"] + area["width"] / 2)) <= 2
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )

    page.locator(toggle).click()
    expect(page.locator(gone)).to_be_visible()
    assert page.locator(kept).bounding_box() == kept_before
    expect(page.locator(toggle)).to_be_visible()


def test_a_game_can_be_played_with_the_bars_hidden(page: Page, seed_prefs):
    """A game can be played with the bars hidden.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    page.goto("/")
    page.locator("#play").click()
    page.locator("#chips .chip", has_text="Your move").wait_for()
    page.locator("#toggle-left").click()
    page.locator("#toggle-right").click()
    click_move(page, "e2", "e4")
    page.locator("#chips .chip", has_text="Your move").wait_for()
    expect(page.locator('.square[data-square="c5"]')).to_have_attribute("data-piece", "bp")
    page.locator("#toggle-right").click()
    expect(page.locator("#movelist .move").first).to_have_text("e4")


def test_board_grows_with_the_window_and_stays_in_view(page: Page):
    """Board grows with the window and stays in view.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator(".square").first.wait_for()
    sizes = []
    for width, height in [(1280, 720), (1366, 768), (1920, 1080), (2560, 1440)]:
        page.set_viewport_size({"width": width, "height": height})
        board = page.locator("#board").bounding_box()
        below = page.locator("#chips").bounding_box()
        assert board["x"] + board["width"] <= width
        assert below["y"] + below["height"] <= height
        sizes.append(board["width"])
    assert sizes == sorted(sizes)
    assert sizes[-1] > sizes[0] * 1.5


def test_fonts_are_the_vendored_ones(page: Page):
    """Fonts are the vendored ones.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator(".square").first.wait_for()
    page.evaluate("document.fonts.ready")
    assert page.evaluate("document.fonts.check('16px \"Familjen Grotesk\"')")
    assert page.evaluate("document.fonts.check('16px \"JetBrains Mono\"')")


def test_logo_is_in_the_header_and_the_browser_tab(page: Page):
    """The logo is at the top of the left bar and is the favicon.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    logo = page.locator(".brand-logo")
    expect(logo).to_be_visible()
    expect(logo).to_have_attribute("alt", "Chess Trainer")
    expect(page).to_have_title("Chess Trainer")
    page.wait_for_function("document.querySelector('.brand-logo').naturalWidth > 0")
    assert abs(logo.bounding_box()["width"] - 95) <= 1
    assert abs(logo.bounding_box()["height"] - 95) <= 1
    assert page.locator('link[rel="icon"]').get_attribute("href") == "logo.svg"
    for path in ("logo.svg", "logo.png"):
        assert page.request.get(f"/{path}").ok


def test_footer_shows_the_engine_version(page: Page):
    """Footer shows the engine version.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    expect(page.locator("#footer-versions")).to_contain_text("Chess Trainer 0.1.0")
    expect(page.locator("#footer-versions")).to_contain_text("Stockfish")


def test_bullet_game_starts_with_thirty_seconds(page: Page, seed_prefs):
    """Bullet game starts with thirty seconds.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], color="white", timeControl="30s")
    page.goto("/")
    options = page.locator('#time-control optgroup[label="Bullet"] option')
    expect(options).to_have_text(["30 s", "1 min", "2 min"])
    expect(page.locator("#time-control")).to_have_value("30s")
    page.locator("#play").click()
    expect(page.locator("#bottom-clock")).to_contain_text("00:30")
    expect(page.locator("#top-clock")).to_contain_text("00:30")


def test_clock_shows_tenths_below_ten_seconds(page: Page):
    """Clock shows tenths below ten seconds.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    shown = page.evaluate(
        """async () => {
            const { formatClock } = await import("/js/clock.js");
            return [125000, 30000, 10001, 10000, 9901, 9900, 1234, 300, 1, 0, -5].map(formatClock);
        }"""
    )
    assert shown == [
        "02:05",
        "00:30",
        "00:11",
        "00:10",
        "00:10",
        "00:09.9",
        "00:01.3",
        "00:00.3",
        "00:00.1",
        "00:00.0",
        "00:00.0",
    ]
