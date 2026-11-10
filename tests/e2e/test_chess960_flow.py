"""The Chess960 setup and a real game against the server."""

import re

from playwright.sync_api import Page, expect

from tests.e2e.conftest import choose_new_game_mode, click_move, square
from tests.e2e.test_board import fake_api, wait_for_sent

# King on f1 between rooks on e1 and g1: castling short only swaps the king and the rook.
SWAP_FEN = "bbqnrkrn/pppppppp/8/8/8/8/PPPPPPPP/BBQNRKRN w KQkq - 0 1"


def open_chess960(page: Page) -> None:
    """Opens the Chess960 setup and waits for its first position.

    Args:
        page (Page): The page.
    """
    page.goto("/")
    choose_new_game_mode(page, "chess960")
    expect(page.locator("#chess960-number")).to_have_text(re.compile(r"Position \d+"))


def back_rank(page: Page) -> list[str | None]:
    """White's back rank, a1 to h1.

    Args:
        page (Page): The page.

    Returns:
        list[str | None]: Each square's piece, such as `wR`, or None.
    """
    return [square(page, f"{file}1").get_attribute("data-piece") for file in "abcdefgh"]


def use_fen(page: Page, fen: str) -> None:
    """Types a starting FEN into the Chess960 setup and submits it.

    Args:
        page (Page): The page.
        fen (str): The FEN.
    """
    page.locator("#chess960-fen").fill(fen)
    page.locator("#chess960-fen-form button").click()


def test_the_die_shows_the_position_on_the_board(page: Page):
    """The die shows the position on the board.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    open_chess960(page)
    rolls = set()
    for _ in range(5):
        with page.expect_response("**/api/chess960") as response:
            page.locator("#chess960-roll").click()
        start = response.value.json()
        rolls.add(start["position"])
        expect(page.locator("#chess960-number")).to_have_text(f"Position {start['position']}")
        rook = "ABCDEFGH"[start["fen"].split(" ")[0].split("/")[7].index("R")].lower()
        expect(square(page, f"{rook}1")).to_have_attribute("data-piece", "wr")
    assert len(rolls) > 1
    # Leaving the mode puts the normal position back.
    choose_new_game_mode(page, "opening")
    expect(square(page, "e1")).to_have_attribute("data-piece", "wk")
    expect(square(page, "a1")).to_have_attribute("data-piece", "wr")


def test_a_fen_shows_its_position_and_anything_else_is_refused(page: Page):
    """A FEN shows its position and anything else is refused.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    open_chess960(page)
    use_fen(page, SWAP_FEN)
    expect(page.locator("#chess960-number")).to_have_text("Position 288")
    expect(square(page, "f1")).to_have_attribute("data-piece", "wk")
    use_fen(page, "r1bqkbnr/pppppppp/2n5/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    expect(page.locator("#chess960-error")).to_be_visible()
    expect(page.locator("#chess960-number")).to_have_text("Position 288")
    expect(square(page, "f1")).to_have_attribute("data-piece", "wk")


def test_black_sees_the_position_and_the_bot_opens(page: Page, seed_prefs):
    """Black sees the position and the bot opens.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([], color="black", timeControl="none")
    open_chess960(page)
    use_fen(page, SWAP_FEN)
    expect(page.locator("#chess960-number")).to_have_text("Position 288")
    page.locator("#play").click()
    page.locator("#chips .chip", has_text="Your move").wait_for()
    expect(page.locator("#movelist .move").first).to_have_text(re.compile(r"\S"))


def test_a_game_castles_and_survives_a_reload(page: Page, seed_prefs):
    """A game castles and survives a reload.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([], color="white", timeControl="none")
    open_chess960(page)
    use_fen(page, SWAP_FEN)
    expect(page.locator("#chess960-number")).to_have_text("Position 288")
    page.locator("#play").click()
    page.locator("#chips .chip", has_text="Your move").wait_for()
    expect(page.locator("#chips .chip", has_text="theory")).to_have_count(0)
    click_move(page, "f1", "g1")
    expect(page.locator("#movelist .move").first).to_have_text("O-O")
    expect(square(page, "g1")).to_have_attribute("data-piece", "wk")
    expect(square(page, "f1")).to_have_attribute("data-piece", "wr")
    expect(page.locator("#movelist .move").nth(1)).to_have_text(re.compile(r"\S"))
    expect(page.locator("#movelist .out")).to_have_count(0)

    page.reload()
    expect(page.locator("#movelist .move").first).to_have_text("O-O")
    expect(square(page, "g1")).to_have_attribute("data-piece", "wk")
    page.locator("#chips .chip", has_text="Your move").wait_for()


def test_clicking_a_square_between_castles_and_sends_king_takes_rook(page: Page, seed_prefs):
    """Clicking a square between castles and sends king takes rook.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([], color="white", timeControl="none")
    sent = fake_api(page, [("a7a6", "a6"), ("b7b6", "b6"), ("c7c6", "c6"), ("d7d6", "d6")])
    open_chess960(page)
    # Position 518 looks like normal chess, but castling works as in Chess960.
    use_fen(page, "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    expect(page.locator("#chess960-number")).to_have_text("Position 518")
    page.locator("#play").click()
    page.locator("#chips .chip", has_text="Your move").wait_for()
    for origin, target in (("e2", "e4"), ("g1", "f3"), ("f1", "c4")):
        click_move(page, origin, target)
        page.locator("#chips .chip", has_text="Your move").wait_for()
    click_move(page, "e1", "g1")
    wait_for_sent(page, sent, 4)
    assert sent[-1]["uci"] == "e1h1"
    expect(square(page, "g1")).to_have_attribute("data-piece", "wk")
    expect(square(page, "f1")).to_have_attribute("data-piece", "wr")
