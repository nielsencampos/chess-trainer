"""Move notation on screen (#53): figurines, English letters or the UI language's letters."""

from playwright.sync_api import Page, expect

from tests.e2e.conftest import BASE_URL, click_move, play, wait_for_ply, wait_for_your_move

ITALIAN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5"
YOUR_MOVE = {"en-US": "Your move", "pt-BR": "Sua vez", "de": "Du bist am Zug"}


def resign(page: Page) -> None:
    """Resigns with the two clicks, in any language, and waits for the end-of-game card.

    Args:
        page (Page): The page.
    """
    page.locator("#resign").click()
    page.locator("#resign").click()
    page.locator("#end-card").wait_for(state="visible")


def shown_moves(page: Page) -> list[str]:
    """The moves of the move list as they look: a figurine reads as `[N]`.

    Args:
        page (Page): The page.

    Returns:
        list[str]: One text per non-empty cell.
    """
    return page.evaluate(
        """() => [...document.querySelectorAll('#movelist .move .notation')].map((move) =>
          [...move.childNodes].map((node) =>
            node.classList?.contains('figurine') ? `[${node.textContent}]` : node.textContent,
          ).join(''))"""
    )


def start_italian(page: Page, seed_prefs, **prefs: str) -> None:
    """Plays 1. e4 and 2. Nf3 of the Italian as White, and leaves it at White's third move.

    Args:
        page (Page): The page.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
        **prefs (str): Other preferences, such as `locale` and `notation`.
    """
    seed_prefs([ITALIAN], color="white", timeControl="none", **prefs)
    your_move = YOUR_MOVE[prefs.get("locale", "en-US")]
    page.goto("/")
    play(page)
    wait_for_your_move(page, your_move)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page, your_move)
    click_move(page, "g1", "f3")
    wait_for_ply(page, 4)
    wait_for_your_move(page, your_move)


def test_figurines_are_the_default_and_copy_as_english_san(page: Page, seed_prefs):
    """Figurines by default, the white Merida piece, with the English letter as text.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    start_italian(page, seed_prefs)
    assert shown_moves(page) == ["e4", "e5", "[N]f3", "[N]c6"]
    knight = page.locator("#movelist .figurine-N").first
    image = knight.evaluate("(element) => getComputedStyle(element).backgroundImage")
    assert "pieces/merida/wN.svg" in image
    assert page.locator("#movelist .move").nth(2).text_content() == "Nf3"
    expect(page.locator("#notation-picker")).to_have_value("figurines")


def test_the_same_game_in_each_language_and_notation(page: Page, seed_prefs):
    """The picker redraws the move list mid-game: English, pt-BR and de letters, and figurines.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    start_italian(page, seed_prefs, locale="en-US", notation="english")
    assert shown_moves(page) == ["e4", "e5", "Nf3", "Nc6"]
    page.locator("#notation-picker").select_option("local")
    assert shown_moves(page) == ["e4", "e5", "Nf3", "Nc6"]  # English letters are its own

    page.locator("#locale-picker").select_option("pt-BR")
    expect(page.locator("#movelist .move").nth(2)).to_have_text("Cf3")
    assert shown_moves(page) == ["e4", "e5", "Cf3", "Cc6"]
    page.locator("#locale-picker").select_option("de")
    expect(page.locator("#movelist .move").nth(2)).to_have_text("Sf3")
    assert shown_moves(page) == ["e4", "e5", "Sf3", "Sc6"]
    page.locator("#notation-picker").select_option("figurines")
    assert shown_moves(page) == ["e4", "e5", "[N]f3", "[N]c6"]

    # The game goes on, and the bot's reply follows the notation too.
    click_move(page, "f1", "c4")
    wait_for_ply(page, 6)
    assert shown_moves(page)[4] == "[B]c4"


def test_the_quick_switch_cycles_and_is_kept(page: Page, seed_prefs):
    """The move list's switch cycles the three notations, moves the picker, and is kept.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    start_italian(page, seed_prefs, locale="pt-BR", notation="local")
    switch = page.locator("#notation-switch")
    expect(switch).to_have_attribute(
        "aria-label",
        "Notação: Letras em português. Mudar para Letras em inglês (internacional, PGN)",
    )
    switch.click()
    expect(page.locator("#notation-picker")).to_have_value("english")
    assert shown_moves(page)[2] == "Nf3"
    switch.click()
    expect(page.locator("#notation-picker")).to_have_value("figurines")
    assert shown_moves(page)[2] == "[N]f3"
    switch.click()
    expect(page.locator("#notation-picker")).to_have_value("local")
    switch.click()
    page.reload()
    page.locator("#movelist .move").nth(3).wait_for()
    expect(page.locator("#notation-picker")).to_have_value("english")
    assert shown_moves(page) == ["e4", "e5", "Nf3", "Nc6"]


def test_hover_and_focus_show_the_other_two_notations(page: Page, seed_prefs):
    """A move shows its other two notations in a tip, on hover and on keyboard focus.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    start_italian(page, seed_prefs, locale="pt-BR", notation="local")
    tip = page.locator(".notation-tip")
    page.locator("#movelist .move .notation").nth(2).hover()
    expect(tip).to_be_visible()
    expect(tip).to_have_text("Nf3 · Nf3")  # English letters, then the figurine's text
    expect(tip.locator(".figurine-N")).to_have_count(1)

    page.mouse.move(5, 700)
    expect(tip).to_be_hidden()
    page.locator("#movelist .move").nth(3).focus()
    expect(tip).to_be_visible()
    expect(tip).to_have_text("Nc6 · Nc6")


def test_the_end_card_follows_the_notation(page: Page, seed_prefs):
    """The deviation and the expected move on the end card are in the chosen notation.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    start_italian(page, seed_prefs, locale="de", notation="local")
    click_move(page, "f1", "b5")  # the book has 3. Bc4
    wait_for_ply(page, 6)
    wait_for_your_move(page, YOUR_MOVE["de"])
    resign(page)
    deviation = page.locator("#end-deviations li")
    expect(deviation).to_have_text("3. Lb5 — erwartet: Lc4")
    page.locator("#notation-picker").select_option("english")
    expect(deviation).to_have_text("3. Bb5 — erwartet: Bc4")
    page.locator("#notation-picker").select_option("figurines")
    expect(deviation.locator(".figurine-B")).to_have_count(2)


def test_the_pgn_is_english_san_whatever_the_notation(page: Page, context, seed_prefs):
    """The copied PGN is the same in every notation, in English SAN.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        context (BrowserContext): The page's browser context.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE_URL)
    start_italian(page, seed_prefs, locale="de", notation="local")
    resign(page)
    copies = []
    for notation in ("local", "english", "figurines"):
        page.locator("#notation-picker").select_option(notation)
        page.locator("#copy-pgn").click()
        copies.append(page.evaluate("navigator.clipboard.readText()"))
    assert copies[0] == copies[1] == copies[2]
    assert "1. e4 e5 2. Nf3 Nc6" in copies[0]


def test_search_finds_lines_by_english_and_local_letters(page: Page):
    """Openings search matches moves in English and in the UI language's letters.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.add_init_script(
        "localStorage.setItem('chess-trainer.prefs', JSON.stringify({locale: 'pt-BR'}))"
    )
    page.goto("/")
    page.locator("#tab-openings").click()
    search = page.locator("#lines-search")
    none = page.locator("#lines-no-matches")
    for query in ("2. Cf3 Cc6 3. Bc4", "2.Nf3 Nc6 3.Bc4"):
        search.fill(query)
        expect(none).to_be_hidden()
    search.fill("2. Sf3 Sc6")  # German letters are not this language's
    expect(none).to_be_visible()
