"""Captures the Help screen's pictures and animations from a running app, in every language.

The pictures are screenshots of the real app at 1280x720, so they follow the UI: run this again
after a visible change. It plays and resigns games, so run it against a disposable app.

    uv run python scripts/help_media.py --base-url http://127.0.0.1:8000

Writes `web/help/<locale>/<name>.webp`.
"""

import argparse
import io
import json
from collections.abc import Callable
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image
from playwright.sync_api import Page, sync_playwright

LOCALES = ["en", "pt-BR", "es"]
VIEWPORT = {"width": 1280, "height": 720}
WIDTH = 960  # Largest output width; the help column is narrower, so this stays sharp.
SIDEBAR = 380  # The left bar's default width, cropped out of the pictures of the board.
QUALITY = 80
LINE = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. Nc3 Nf6 5. O-O O-O 6. d3"
OUT = Path(__file__).resolve().parent.parent / "web" / "help"


def fetch_json(url: str, method: str = "GET") -> dict:
    """Calls the app's API.

    Args:
        url (str): The full URL.
        method (str): The HTTP method.

    Returns:
        dict: The decoded JSON body, or an empty dict when there is none.
    """
    with urlopen(Request(url, method=method)) as response:
        body = response.read()
    return json.loads(body) if body else {}


def resign_active_game(base_url: str) -> None:
    """Resigns the app's unfinished game, if any, so the next page starts at the menu.

    Args:
        base_url (str): The app's address.
    """
    game = fetch_json(f"{base_url}/api/games/active")["game"]
    if game and not game["state"]["game_over"]:
        fetch_json(f"{base_url}/api/games/{game['state']['game_id']}/resign", method="POST")


def line_id(base_url: str) -> str:
    """The id of the book line the pictures play.

    Args:
        base_url (str): The app's address.

    Returns:
        str: The line's id.

    Raises:
        LookupError: The line is not in the book.
    """
    for repertoire in fetch_json(f"{base_url}/api/repertoires")["repertoires"]:
        for variant in repertoire["variants"]:
            if variant["pgn"] == LINE:
                return variant["variant_id"]
    raise LookupError(LINE)


def frame(page: Page, board_only: bool = True) -> Image.Image:
    """A screenshot of the page, at most the output width.

    Args:
        page (Page): The page.
        board_only (bool): Crop out the left bar, so the board shows larger.

    Returns:
        Image.Image: The frame.
    """
    image = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    if board_only:
        image = image.crop((SIDEBAR, 0, image.width, image.height))
    if image.width <= WIDTH:
        return image
    height = round(image.height * WIDTH / image.width)
    return image.resize((WIDTH, height), Image.Resampling.LANCZOS)


def save(path: Path, frames: list[Image.Image], durations: list[int] | None = None) -> None:
    """Writes one picture, or an animation that loops when there are several frames.

    Args:
        path (Path): The output file.
        frames (list[Image.Image]): The frames.
        durations (list[int] | None): Milliseconds per frame, for an animation.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(frames) == 1:
        frames[0].save(path, "WEBP", quality=QUALITY, method=6)
    else:
        frames[0].save(
            path,
            "WEBP",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            quality=QUALITY,
            method=6,
        )
    print(f"{path.relative_to(OUT.parent.parent)}: {path.stat().st_size // 1024} KB")


def square(page: Page, name: str):
    """A square of the board.

    Args:
        page (Page): The page.
        name (str): The square, such as `e4`.

    Returns:
        Locator: The square's element.
    """
    return page.locator(f'.square[data-square="{name}"]')


def wait_for_ply(page: Page, ply: int) -> None:
    """Waits until the game has that many plies, and the board has settled.

    Args:
        page (Page): The page.
        ply (int): The number of plies.
    """
    page.wait_for_function(
        "(ply) => [...document.querySelectorAll('#movelist .move')]"
        ".filter((cell) => cell.textContent).length >= ply",
        arg=ply,
    )
    page.wait_for_timeout(400)


def drag(page: Page, origin: str, target: str) -> None:
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


def capture_locale(new_page: Callable[[dict], Page], base_url: str, locale: str) -> None:
    """Captures every picture of one language.

    Args:
        new_page (Callable[[dict], Page]): Opens a fresh page with these preferences stored.
        base_url (str): The app's address.
        locale (str): The language.
    """
    out = OUT / locale
    prefs = {
        "locale": locale,
        "selected": [line_id(base_url)],
        "color": "white",
        "level": "warmup",
        "pace": "instant",
        "timeControl": "25",
        "showMoves": True,
    }
    resign_active_game(base_url)
    page = new_page(prefs)
    page.goto("/")
    page.locator("#play").wait_for(state="visible")
    page.wait_for_function("!document.querySelector('#play').disabled")
    page.wait_for_timeout(500)
    save(out / "setup.webp", [frame(page, board_only=False)])

    # Playing: select a piece (dots on its targets), move it, the bot's book reply, a drag.
    page.locator("#play").click()
    page.locator("#game-card").wait_for(state="visible")
    page.wait_for_timeout(400)
    frames = [frame(page)]
    square(page, "e2").click()
    page.wait_for_timeout(200)
    frames.append(frame(page))
    square(page, "e4").click()
    frames.append(frame(page))
    wait_for_ply(page, 2)
    frames.append(frame(page))
    drag(page, "g1", "f3")
    frames.append(frame(page))
    wait_for_ply(page, 4)
    frames.append(frame(page))
    save(out / "play.webp", frames, [1400, 1100, 700, 1400, 900, 2200])

    # Writing on paper: untick Show moves and keep playing with the list hidden.
    frames = [frame(page)]
    page.locator("#show-moves").uncheck()
    page.wait_for_timeout(300)
    frames.append(frame(page))
    square(page, "f1").click()
    square(page, "c4").click()
    frames.append(frame(page))
    wait_for_ply(page, 6)
    frames.append(frame(page))
    save(out / "paper.webp", frames, [1600, 1600, 900, 2200])

    # The end of the game: resign (two clicks), and the card under the move list.
    page.locator("#resign").click()
    page.locator("#resign").click()
    page.locator("#end-card").wait_for(state="visible")
    page.wait_for_timeout(800)
    save(out / "end.webp", [frame(page)])

    # Reviewing it: the evaluation bar and the move icons.
    page.locator("#tab-saved").click()
    page.locator("#saved-list .saved-game").first.wait_for()
    page.locator("#saved-list .view-button").first.click()
    page.locator("#review-bar").wait_for(state="visible")
    page.locator("#review-first").click()
    for _ in range(4):
        page.locator("#review-next").click()
    page.wait_for_timeout(2500)
    save(out / "review.webp", [frame(page)])
    page.close()


def main() -> None:
    """Captures the pictures of every language."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    base_url = parser.parse_args().base_url.rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        def new_page(prefs: dict) -> Page:
            """Opens a fresh page with these preferences stored before any script runs.

            Args:
                prefs (dict): The preferences.

            Returns:
                Page: The page.
            """
            context = browser.new_context(
                base_url=base_url, viewport=VIEWPORT, color_scheme="light"
            )
            context.add_init_script(
                f"localStorage.setItem('chess-trainer.prefs', {json.dumps(json.dumps(prefs))});"
            )
            return context.new_page()

        for locale in LOCALES:
            capture_locale(new_page, base_url, locale)
        browser.close()


if __name__ == "__main__":
    main()
