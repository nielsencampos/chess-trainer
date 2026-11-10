"""Browser flows against a running app.

Run with: E2E_BASE_URL=http://127.0.0.1:8000 uv run pytest -m e2e
"""

import json
import os
from urllib.request import Request, urlopen

import pytest
from playwright.sync_api import Page

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000")

VIEWPORT = {"width": 1280, "height": 720}  # HD is the smallest supported screen


@pytest.fixture(scope="session")
def all_variants() -> list[dict]:
    """Every line of the running app's book.

    Returns:
        list[dict]: The lines, as `/api/repertoires` gives them.
    """
    with urlopen(f"{BASE_URL}/api/repertoires") as response:
        repertoires = json.load(response)["repertoires"]
    return [variant for repertoire in repertoires for variant in repertoire["variants"]]


@pytest.fixture
def context(browser):
    """A browser context on the app at 1280x720, the smallest supported screen.

    Args:
        browser (Browser): Playwright's browser.

    Yields:
        BrowserContext: The context, closed after the test.
    """
    context = browser.new_context(base_url=BASE_URL, viewport=VIEWPORT)
    yield context
    context.close()


def resign_active_game() -> None:
    """Resigns the app's unfinished game, if any: it would be resumed by the next test."""
    with urlopen(f"{BASE_URL}/api/games/active") as response:
        game = json.load(response)["game"]
    if game and not game["state"]["game_over"]:
        request = Request(f"{BASE_URL}/api/games/{game['state']['game_id']}/resign", method="POST")
        urlopen(request).close()


@pytest.fixture
def page(context) -> Page:
    """A fresh page; an uncaught page error fails the test.

    Args:
        context (BrowserContext): The browser context.

    Yields:
        Page: The page.
    """
    resign_active_game()
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    assert errors == [], f"uncaught page errors: {errors}"


@pytest.fixture
def seed_prefs(page: Page, all_variants):
    """Stores setup preferences so a test starts with exactly the given variations selected.

    Args:
        page (Page): The page.
        all_variants (list[dict]): The book's lines, to find ids by PGN.

    Returns:
        Callable[..., None]: `seed(selected_pgns, **prefs)`, with the Instant pace and the
            Warm-up level by default.
    """
    ids_by_pgn = {variant["pgn"]: variant["variant_id"] for variant in all_variants}

    def seed(selected_pgns: list[str], **prefs) -> None:
        """Writes the preferences before the page's scripts run, unless some are already stored.

        Args:
            selected_pgns (list[str]): The PGNs of the lines to select.
            **prefs (object): Other preferences, such as `color` or `timeControl`.
        """
        selected = [ids_by_pgn[pgn] for pgn in selected_pgns]
        stored = json.dumps({"selected": selected, "pace": "instant", "level": "warmup", **prefs})
        page.add_init_script(
            f"if (!localStorage.getItem('chess-trainer.prefs')) "
            f"localStorage.setItem('chess-trainer.prefs', {json.dumps(stored)});"
        )

    return seed


def square(page: Page, name: str):
    """A square of the board.

    Args:
        page (Page): The page.
        name (str): The square, such as `e4`.

    Returns:
        Locator: The square's element.
    """
    return page.locator(f'.square[data-square="{name}"]')


def choose_new_game_mode(page: Page, mode: str) -> None:
    """Opens New Game and picks how it starts.

    Args:
        page (Page): The page.
        mode (str): `opening`, `saved` or `chess960`.
    """
    page.locator("#tab-new").click()
    page.locator(f'label:has(input[name="new-mode"][value="{mode}"])').click()


def click_move(page: Page, origin: str, target: str) -> None:
    """Moves a piece by clicking its square, then the target.

    Args:
        page (Page): The page.
        origin (str): The piece's square.
        target (str): The target square.
    """
    square(page, origin).click()
    square(page, target).click()


def drag_move(page: Page, origin: str, target: str) -> None:
    """Moves a piece by dragging it.

    Args:
        page (Page): The page.
        origin (str): The piece's square.
        target (str): The target square.
    """
    start = square(page, origin).bounding_box()
    end = square(page, target).bounding_box()
    page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
    page.mouse.down()
    page.mouse.move(end["x"] + end["width"] / 2, end["y"] + end["height"] / 2, steps=6)
    page.mouse.up()


def play(page: Page) -> None:
    """Clicks Play and waits for the game to show.

    Args:
        page (Page): The page.
    """
    page.locator("#play").click()
    page.locator("#game-card").wait_for(state="visible")


def wait_for_ply(page: Page, ply: int) -> None:
    """Waits until the move list shows that many plies.

    Args:
        page (Page): The page.
        ply (int): The number of plies.
    """
    page.wait_for_function(
        "(ply) => [...document.querySelectorAll('#movelist .move')]"
        ".filter((cell) => cell.textContent).length >= ply",
        arg=ply,
    )


def wait_for_your_move(page: Page, text: str = "Your move") -> None:
    """Waits for a status chip, by default the one that says it is the user's move.

    Args:
        page (Page): The page.
        text (str): The chip's text.
    """
    page.locator("#chips .chip", has_text=text).wait_for()


def moves_text(page: Page) -> list[str]:
    """The moves in the move list, in order.

    Args:
        page (Page): The page.

    Returns:
        list[str]: The SAN of each non-empty cell.
    """
    cells = page.locator("#movelist .move").all_text_contents()
    return [cell for cell in cells if cell]
