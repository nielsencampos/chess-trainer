"""Board behavior from brief §4. Positions that a real game cannot reach reliably use scripted
bot moves: the API is replaced in the browser, the frontend and chess.js stay real."""

import json
import re

from playwright.sync_api import Page, expect

from tests.e2e.conftest import click_move, moves_text, play, square, wait_for_your_move


def fake_api(page: Page, bot_moves: list[tuple[str, str]], first_bot_move: bool = False) -> list:
    """Bot replies come from a script. Returns the list of request bodies the app sent."""
    script = list(bot_moves)
    sent: list[dict] = []
    ply = {"value": 0}

    def state(game_over: bool = False) -> dict:
        return {
            "game_id": "fake",
            "fen": "",
            "ply": ply["value"],
            "in_theory": True,
            "theory_until_ply": ply["value"],
            "left_theory_at_move": None,
            "game_over": game_over,
        }

    def bot_move() -> dict | None:
        if not script:
            return None
        uci, san = script.pop(0)
        ply["value"] += 1
        return {
            "uci": uci,
            "san": san,
            "ply": ply["value"],
            "source": "book",
            "delay_ms": 0,
            "in_theory": True,
        }

    def fulfill(route, body: dict, status: int = 200) -> None:
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    def new_game(route) -> None:
        move = bot_move() if first_bot_move else None
        fulfill(route, {"state": state(), "bot_move": move}, 201)

    def move(route) -> None:
        body = route.request.post_data_json
        sent.append(body)
        ply["value"] += 1
        user = {"uci": body["uci"], "san": "x", "ply": ply["value"], "in_theory": True}
        reply = bot_move()
        fulfill(
            route,
            {
                "user_move": user,
                "deviation": None,
                "bot_move": reply,
                "state": state(game_over=not script and reply is None),
            },
        )

    def summary(route) -> None:
        fulfill(
            route,
            {
                "state": state(True),
                "result": "win",
                "termination": "checkmate",
                "variant_id": "fake",
                "variant_names": {"en": "Fake line"},
                "eco": "A00",
                "opening": "Fake",
                "total_plies": ply["value"],
                "deviations": [],
                "moves": [],
                "pgn": "1. f3 *",
                "lichess_url": "https://lichess.org/analysis",
            },
        )

    page.route("**/api/games", new_game)
    page.route("**/api/games/fake/moves", move)
    page.route("**/api/games/fake", summary)
    return sent


PROMOTION_LINE = [
    ("b7b5", "b5"),
    ("a7a6", "a6"),
    ("c8b7", "Bb7"),
    ("b8c6", "Nc6"),
    ("g7g6", "g6"),
]


def reach_promotion(page: Page) -> None:
    for origin, target in [("a2", "a4"), ("a4", "b5"), ("b5", "a6"), ("a6", "b7")]:
        click_move(page, origin, target)
        wait_for_your_move(page)


def test_promotion_picker_is_an_overlay_with_four_pieces(page: Page, seed_prefs):
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    sent = fake_api(page, PROMOTION_LINE)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    reach_promotion(page)

    click_move(page, "b7", "a8")
    picker = page.locator(".board .promotion")
    expect(picker.locator("button")).to_have_count(4)
    assert [b.get_attribute("data-promotion") for b in picker.locator("button").all()] == [
        "q",
        "r",
        "b",
        "n",
    ]
    # Clicking outside cancels and the pawn stays.
    backdrop = page.locator(".promotion-backdrop").bounding_box()
    page.mouse.click(backdrop["x"] + backdrop["width"] - 5, backdrop["y"] + backdrop["height"] - 5)
    expect(picker).to_have_count(0)
    expect(square(page, "b7")).to_have_attribute("data-piece", "wp")

    click_move(page, "b7", "a8")
    picker.locator('button[data-promotion="n"]').click()
    expect(square(page, "a8")).to_have_attribute("data-piece", "wn")
    assert sent[-1]["uci"] == "b7a8n"


def test_check_highlight_and_checkmate_ends_the_game(page: Page, seed_prefs):
    seed_prefs(["1. e4 c6 2. d4 d5 3. e5 Bf5 4. Nf3"], color="black", timeControl="none")
    sent = fake_api(page, [("f2f3", "f3"), ("g2g4", "g4")], first_bot_move=True)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e7", "e5")
    wait_for_your_move(page)
    click_move(page, "d8", "h4")
    expect(square(page, "e1")).to_have_class(re.compile(r"\bcheck\b"))
    assert sent[-1]["uci"] == "d8h4"
    expect(page.locator("#end-result")).to_have_text("You won")
    expect(page.locator("#end-termination")).to_have_text("by checkmate")


def test_check_chip_on_the_users_king(page: Page, seed_prefs):
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    fake_api(page, [("e7e6", "e6"), ("f8b4", "Bb4+")])
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_your_move(page)
    click_move(page, "d2", "d4")
    wait_for_your_move(page)
    expect(page.locator("#chips")).to_contain_text("Check")
    expect(square(page, "e1")).to_have_class(re.compile(r"\bcheck\b"))


def has_class(page: Page, name: str, css_class: str) -> bool:
    return css_class in (square(page, name).get_attribute("class") or "").split()


def test_highlights_selected_targets_captures_and_last_move(page: Page, seed_prefs):
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    fake_api(page, [("d7d5", "d5"), ("g8f6", "Nf6")])
    page.goto("/")
    play(page)
    wait_for_your_move(page)

    square(page, "e2").click()
    assert has_class(page, "e2", "selected")
    assert has_class(page, "e3", "target")
    assert has_class(page, "e4", "target")
    assert not has_class(page, "e5", "target")
    square(page, "e2").click()  # a second click on the piece deselects it
    assert not has_class(page, "e2", "selected")
    assert not has_class(page, "e4", "target")

    click_move(page, "e2", "e4")
    wait_for_your_move(page)
    assert has_class(page, "d7", "last")
    assert has_class(page, "d5", "last")

    square(page, "e4").click()
    assert has_class(page, "d5", "capture")
    assert not has_class(page, "d5", "target")
    assert has_class(page, "e5", "target")

    square(page, "a7").click()  # not the user's piece: clears the selection
    assert not has_class(page, "e4", "selected")


def test_illegal_targets_do_not_move(page: Page, seed_prefs):
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e5")
    expect(square(page, "e2")).to_have_attribute("data-piece", "wp")
    assert moves_text(page) == []


def test_drag_dropped_outside_keeps_the_piece(page: Page, seed_prefs):
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    box = square(page, "e2").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] - box["height"] * 2, steps=5)
    expect(page.locator(".drag-ghost")).to_have_count(1)
    expect(square(page, "e2").locator(".piece")).to_be_hidden()
    page.mouse.move(2, 2, steps=2)
    page.mouse.up()
    expect(page.locator(".drag-ghost")).to_have_count(0)
    expect(square(page, "e2").locator(".piece")).to_be_visible()
    assert moves_text(page) == []


def test_touch_drag_moves_a_piece(browser, seed_prefs, device, page: Page):
    if device != "mobile":
        return
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    scroll_before = page.evaluate("window.scrollY")
    start = square(page, "e2").bounding_box()
    end = square(page, "e4").bounding_box()
    cdp = page.context.new_cdp_session(page)
    x = start["x"] + start["width"] / 2

    def touch(kind: str, y: float | None = None) -> None:
        points = [] if y is None else [{"x": x, "y": y}]
        cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

    from_y = start["y"] + start["height"] / 2
    to_y = end["y"] + end["height"] / 2
    touch("touchStart", from_y)
    for step in range(1, 6):
        touch("touchMove", from_y + (to_y - from_y) * step / 5)
    touch("touchEnd")
    expect(square(page, "e4")).to_have_attribute("data-piece", "wp")
    assert page.evaluate("window.scrollY") == scroll_before


def test_board_flips_to_the_users_color_with_coordinates(page: Page, seed_prefs):
    seed_prefs(["1. e4 c6 2. d4 d5 3. e5 Bf5 4. Nf3"], color="white", timeControl="none")
    page.goto("/")
    first = page.locator(".square").first
    expect(first).to_have_attribute("data-square", "a8")
    expect(page.locator(".coord-rank")).to_have_text([str(n) for n in range(8, 0, -1)])
    expect(page.locator(".coord-file")).to_have_text(list("abcdefgh"))
    expect(square(page, "a1").locator(".coord-rank")).to_have_text("1")
    expect(square(page, "a1").locator(".coord-file")).to_have_text("a")

    page.locator('input[name="color"][value="black"]').check()
    expect(first).to_have_attribute("data-square", "h1")
    expect(page.locator(".coord-rank")).to_have_text([str(n) for n in range(1, 9)])
    expect(page.locator(".coord-file")).to_have_text(list("hgfedcba"))
    expect(square(page, "h8").locator(".coord-rank")).to_have_text("8")
    expect(square(page, "h8").locator(".coord-file")).to_have_text("h")


def test_board_colors_a1_is_dark(page: Page):
    page.goto("/")
    color = "(element) => getComputedStyle(element).backgroundColor"
    assert square(page, "a1").evaluate(color) == "rgb(118, 150, 86)"
    assert square(page, "h1").evaluate(color) == "rgb(238, 238, 210)"


def test_all_piece_sets_load(page: Page):
    page.goto("/")
    select = page.locator("#piece-set")
    expect(select.locator("option")).to_have_text(
        ["Merida", "Cburnett", "Chessnut", "Fantasy", "Unicode"]
    )
    for key in ("merida", "cburnett", "chessnut", "fantasy"):
        select.select_option(key)
        expect(square(page, "e1").locator("img")).to_have_attribute("src", f"pieces/{key}/wK.svg")
        page.wait_for_function(
            "[...document.querySelectorAll('.square img')]"
            ".every((image) => image.complete && image.naturalWidth > 0)"
        )
    select.select_option("unicode")
    expect(square(page, "e1").locator(".piece-glyph")).to_contain_text("♚")
    loaded = page.evaluate("""document.fonts.load('40px "Noto Sans Symbols 2"', '♚')""")
    assert page.evaluate("(count) => count", len(loaded)) > 0

    page.reload()
    expect(page.locator("#piece-set")).to_have_value("unicode")
