"""Browser flows against a running app: E2E_BASE_URL=http://127.0.0.1:8000 uv run pytest -m e2e"""

import json
import os
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000")

VIEWPORT = {"width": 1280, "height": 800}


@pytest.fixture(scope="session")
def all_variants() -> list[dict]:
    with urlopen(f"{BASE_URL}/api/repertoires") as response:
        repertoires = json.load(response)["repertoires"]
    return [variant for repertoire in repertoires for variant in repertoire["variants"]]


@pytest.fixture
def context(browser):
    context = browser.new_context(base_url=BASE_URL, viewport=VIEWPORT)
    yield context
    context.close()


@pytest.fixture
def page(context) -> Page:
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    assert errors == [], f"uncaught page errors: {errors}"


@pytest.fixture
def seed_prefs(page: Page, all_variants):
    """Stores setup preferences so a test starts with exactly the given variations selected."""

    ids_by_pgn = {variant["pgn"]: variant["variant_id"] for variant in all_variants}

    def seed(selected_pgns: list[str], **prefs) -> None:
        selected = [ids_by_pgn[pgn] for pgn in selected_pgns]
        stored = json.dumps({"selected": selected, "pace": "instant", "level": "warmup", **prefs})
        page.add_init_script(
            f"if (!localStorage.getItem('chess-trainer.prefs')) "
            f"localStorage.setItem('chess-trainer.prefs', {json.dumps(stored)});"
        )

    return seed


def square(page: Page, name: str):
    return page.locator(f'.square[data-square="{name}"]')


def click_move(page: Page, origin: str, target: str) -> None:
    square(page, origin).click()
    square(page, target).click()


def drag_move(page: Page, origin: str, target: str) -> None:
    start = square(page, origin).bounding_box()
    end = square(page, target).bounding_box()
    page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
    page.mouse.down()
    page.mouse.move(end["x"] + end["width"] / 2, end["y"] + end["height"] / 2, steps=6)
    page.mouse.up()


def play(page: Page) -> None:
    page.locator("#play").click()
    page.locator("#game-card").wait_for(state="visible")


def wait_for_ply(page: Page, ply: int) -> None:
    """Waits until the move list shows that many plies."""
    page.wait_for_function(
        "(ply) => [...document.querySelectorAll('#movelist .move')]"
        ".filter((cell) => cell.textContent).length >= ply",
        arg=ply,
    )


def wait_for_your_move(page: Page) -> None:
    page.locator("#chips .chip", has_text="Your move").wait_for()


def moves_text(page: Page) -> list[str]:
    cells = page.locator("#movelist .move").all_text_contents()
    return [cell for cell in cells if cell]
