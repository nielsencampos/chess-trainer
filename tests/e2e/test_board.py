"""Board behavior from brief §4. Positions that a real game cannot reach reliably use scripted
bot moves: the API is replaced in the browser, the frontend and its rules stay real."""

import json
import re

from playwright.sync_api import Page, expect

from tests.e2e.conftest import click_move, moves_text, play, square, wait_for_your_move


def fake_api(
    page: Page,
    bot_moves: list[tuple[str, str]],
    first_bot_move: bool = False,
    delay_ms: int = 0,
) -> list:
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
            "delay_ms": delay_ms,
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


def test_pieces_are_merida(page: Page):
    page.goto("/")
    expect(page.locator("#piece-set")).to_have_count(0)
    expect(square(page, "e1").locator("img")).to_have_attribute("src", "pieces/merida/wK.svg")
    page.wait_for_function(
        "[...document.querySelectorAll('.square img')]"
        ".every((image) => image.complete && image.naturalWidth > 0)"
    )


PREMOVE_LINE = [("a7a6", "a6"), ("b7b6", "b6"), ("c7c6", "c6"), ("d7d6", "d6")]


def start_with_premoves(page: Page, seed_prefs, line, **options) -> list:
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none", **options)
    sent = fake_api(page, line, delay_ms=700)
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    return sent


def wait_for_sent(page: Page, sent: list, count: int) -> None:
    for _ in range(100):
        if len(sent) >= count:
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"expected {count} moves, got {sent}")


def test_premove_plays_as_soon_as_the_bot_replies(page: Page, seed_prefs):
    sent = start_with_premoves(page, seed_prefs, PREMOVE_LINE)
    click_move(page, "e2", "e4")
    click_move(page, "d2", "d4")
    assert has_class(page, "d2", "premove")
    assert has_class(page, "d4", "premove")
    expect(page.locator("#chips")).to_contain_text("Premove set")
    wait_for_sent(page, sent, 2)
    assert [move["uci"] for move in sent] == ["e2e4", "d2d4"]
    expect(square(page, "d4")).to_have_attribute("data-piece", "wp")
    assert not has_class(page, "d4", "premove")
    expect(page.locator("#chips")).not_to_contain_text("Premove set")


def test_illegal_premove_is_dropped_and_it_stays_the_users_turn(page: Page, seed_prefs):
    sent = start_with_premoves(page, seed_prefs, PREMOVE_LINE)
    click_move(page, "e2", "e4")
    click_move(page, "e4", "d5")  # a capture that needs a black piece on d5, which never comes
    assert has_class(page, "d5", "premove")
    wait_for_your_move(page)
    page.wait_for_timeout(200)
    assert [move["uci"] for move in sent] == ["e2e4"]
    expect(square(page, "e4")).to_have_attribute("data-piece", "wp")
    assert not has_class(page, "d5", "premove")


def test_right_click_cancels_a_premove(page: Page, seed_prefs):
    sent = start_with_premoves(page, seed_prefs, PREMOVE_LINE)
    click_move(page, "e2", "e4")
    click_move(page, "d2", "d4")
    square(page, "h4").click(button="right")
    assert not has_class(page, "d2", "premove")
    expect(page.locator("#chips")).not_to_contain_text("Premove set")
    wait_for_your_move(page)
    page.wait_for_timeout(200)
    assert [move["uci"] for move in sent] == ["e2e4"]


def test_clicking_elsewhere_cancels_a_premove(page: Page, seed_prefs):
    sent = start_with_premoves(page, seed_prefs, PREMOVE_LINE)
    click_move(page, "e2", "e4")
    click_move(page, "d2", "d4")
    square(page, "h5").click()
    assert not has_class(page, "d2", "premove")
    wait_for_your_move(page)
    page.wait_for_timeout(200)
    assert [move["uci"] for move in sent] == ["e2e4"]


def test_premove_can_be_turned_off(page: Page, seed_prefs):
    sent = start_with_premoves(page, seed_prefs, PREMOVE_LINE, premoves=False)
    click_move(page, "e2", "e4")
    click_move(page, "d2", "d4")
    assert not has_class(page, "d2", "premove")
    wait_for_your_move(page)
    page.wait_for_timeout(200)
    assert [move["uci"] for move in sent] == ["e2e4"]


def test_premove_before_the_bots_first_move(page: Page, seed_prefs):
    seed_prefs(["1. e4 c5 2. c3"], color="black", timeControl="none")
    sent = fake_api(page, [("e2e4", "e4"), ("d2d4", "d4")], first_bot_move=True, delay_ms=1500)
    page.goto("/")
    play(page)
    click_move(page, "c7", "c5")
    assert has_class(page, "c5", "premove")
    wait_for_sent(page, sent, 1)
    assert sent[0]["uci"] == "c7c5"


def test_premove_promotes_to_a_queen(page: Page, seed_prefs):
    sent = start_with_premoves(page, seed_prefs, PROMOTION_LINE)
    for origin, target in [("a2", "a4"), ("a4", "b5"), ("b5", "a6")]:
        click_move(page, origin, target)
        wait_for_your_move(page)
    click_move(page, "a6", "b7")
    click_move(page, "b7", "a8")
    expect(page.locator(".board .promotion")).to_have_count(0)
    wait_for_sent(page, sent, 5)
    assert sent[-1]["uci"] == "b7a8q"
    expect(square(page, "a8")).to_have_attribute("data-piece", "wq")


def test_premove_destinations_by_shape(page: Page):
    page.goto("/")
    page.locator(".square").first.wait_for()
    result = page.evaluate(
        """async () => {
          const { premoveDestinations: at } = await import("/js/premove.js");
          return {
            whitePawn: at("e2", { color: "w", type: "p" }),
            blackPawn: at("a7", { color: "b", type: "p" }),
            knight: at("a1", { color: "w", type: "n" }),
            king: at("e1", { color: "w", type: "k" }),
            rook: at("a1", { color: "w", type: "r" }).length,
            queen: at("d4", { color: "w", type: "q" }).length,
          };
        }"""
    )
    assert sorted(result["whitePawn"]) == ["d3", "e3", "e4", "f3"]
    assert sorted(result["blackPawn"]) == ["a5", "a6", "b6"]
    assert sorted(result["knight"]) == ["b3", "c2"]
    assert sorted(result["king"]) == ["c1", "d1", "d2", "e2", "f1", "f2", "g1"]
    assert result["rook"] == 14
    assert result["queen"] == 27


RECORD_SOUNDS = """
window.sounds = [];
document.addEventListener("chess-trainer:sound", (event) => window.sounds.push(event.detail));
"""


def sounds(page: Page) -> list[str]:
    return [
        f"{item['type']}{'-bot' if item['byBot'] else ''}"
        for item in page.evaluate("window.sounds")
    ]


def test_each_event_plays_its_sound(page: Page, seed_prefs):
    page.add_init_script(RECORD_SOUNDS)
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    fake_api(
        page,
        [
            ("d7d5", "d5"),
            ("a7a6", "a6"),
            ("b7b6", "b6"),
            ("g7g6", "g6"),
            ("h7h6", "h6"),
            ("a6a5", "a5"),
        ],
    )
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_your_move(page)
    click_move(page, "e4", "d5")  # capture
    wait_for_your_move(page)
    click_move(page, "g1", "f3")
    wait_for_your_move(page)
    click_move(page, "f1", "c4")
    wait_for_your_move(page)
    click_move(page, "e1", "g1")  # castling
    wait_for_your_move(page)
    assert sounds(page) == [
        "start",
        "move",
        "move-bot",
        "capture",
        "move-bot",
        "move",
        "move-bot",
        "move",
        "move-bot",
        "castle",
        "move-bot",
    ]


def test_bot_capture_and_castling_sound_like_the_bots(page: Page, seed_prefs):
    page.add_init_script(RECORD_SOUNDS)
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    fake_api(page, [("d7d5", "d5"), ("d5e4", "dxe4"), ("a7a6", "a6")])
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_your_move(page)
    click_move(page, "g1", "f3")
    wait_for_your_move(page)
    assert "capture-bot" in sounds(page)


def test_game_end_plays_a_sound_and_a_reload_stays_silent(page: Page, seed_prefs):
    page.add_init_script(RECORD_SOUNDS)
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    page.reload()  # no click yet in this page: the browser allows no audio
    wait_for_your_move(page)
    assert sounds(page) == []
    click_move(page, "e2", "e4")  # the first click allows it
    wait_for_your_move(page)
    assert sounds(page)[-1] == "move-bot"
    page.locator("#resign").click()
    page.locator("#resign").click()
    page.locator("#end-card").wait_for(state="visible")
    assert sounds(page)[-1] == "end"


def test_sound_can_be_turned_off_and_the_choice_is_kept(page: Page, seed_prefs):
    page.add_init_script(RECORD_SOUNDS)
    seed_prefs(["1. e4 c5 2. c3"], color="white", timeControl="none")
    fake_api(page, [("d7d5", "d5"), ("a7a6", "a6")])
    page.goto("/")
    toggle = page.locator("#sound-toggle")
    expect(toggle).to_have_text("Sound: on")
    toggle.click()
    expect(toggle).to_have_text("Sound: off")
    expect(page.locator("#sound-volume")).to_be_disabled()
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_your_move(page)
    assert sounds(page) == []
    page.reload()
    expect(page.locator("#sound-toggle")).to_have_text("Sound: off")


def test_volume_is_kept(page: Page):
    page.goto("/")
    slider = page.locator("#sound-volume")
    expect(slider).to_have_value("0.7")
    slider.fill("0.3")
    page.reload()
    expect(page.locator("#sound-volume")).to_have_value("0.3")


def test_generated_sounds_are_audible_and_different(page: Page):
    page.goto("/")
    page.locator(".square").first.wait_for()
    result = page.evaluate(
        """async () => {
          const { scheduleSound } = await import("/js/sound.js");
          const render = async (type, byBot = false) => {
            const context = new OfflineAudioContext(1, 44100, 44100);
            scheduleSound(context, context.destination, type, 0, byBot);
            const samples = (await context.startRendering()).getChannelData(0);
            let peak = 0, last = 0, energy = 0, crossings = 0;
            for (let i = 0; i < samples.length; i += 1) {
              const value = Math.abs(samples[i]);
              if (value > peak) peak = value;
              if (value > 0.001) last = i;
              energy += samples[i] * samples[i];
              // Just after the click and before a second knock: this window shows the pitch.
              if (i > 900 && i < 2500 && samples[i - 1] * samples[i] < 0) crossings += 1;
            }
            return { peak, seconds: last / 44100, energy, crossings };
          };
          const out = {};
          for (const type of ["move", "capture", "castle", "start", "end"]) {
            out[type] = await render(type);
          }
          out.bot = await render("move", true);
          return out;
        }"""
    )
    for name, item in result.items():
        assert item["peak"] > 0.05, name
        assert item["seconds"] < 0.8, name
    assert result["capture"]["energy"] > result["move"]["energy"]
    assert result["capture"]["crossings"] < result["move"]["crossings"]  # lower pitch
    assert result["castle"]["seconds"] > result["move"]["seconds"]  # two knocks
    assert result["bot"]["crossings"] < result["move"]["crossings"]
    assert result["end"]["seconds"] > result["start"]["seconds"]
