"""Language picker (brief §8): switching redraws the page in place and is kept after a reload."""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import click_move, play, wait_for_ply, wait_for_your_move

ALAPIN = "1. e4 c5 2. c3"


def test_picker_lists_each_language_in_its_own_name(page: Page):
    """Picker lists each language in its own name.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    options = page.locator("#locale-picker option")
    expect(options).to_have_text(
        [
            "English (US)",
            "Dansk",
            "Deutsch",
            "English (UK)",
            "Español (Latinoamérica)",
            "Español (España)",
            "Suomi",
            "Français",
            "Bahasa Indonesia",
            "Italiano",
            "Norsk bokmål",
            "Nederlands",
            "Polski",
            "Português (Brasil)",
            "Português (Portugal)",
            "Русский",
            "Svenska",
            "Türkçe",
            "Українська",
            "Tiếng Việt",
        ]
    )
    expect(page.locator("#locale-picker")).to_have_value("en-US")


def test_a_latin_extended_language_loads_its_font_subset(page: Page):
    """Turkish text uses the vendored latin-ext faces, not a system font mid-word.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator("#locale-picker").select_option("tr")
    expect(page.locator("html")).to_have_attribute("lang", "tr")
    expect(page.locator("#tab-scoresheet")).to_have_text(
        "Hamle K\u00e2\u011f\u0131d\u0131"
    )  # Turkish dotless i
    loaded = page.evaluate(
        """async () => {
          await document.fonts.ready;
          return [...document.fonts]
            .filter((face) => face.status === "loaded" && face.unicodeRange.startsWith("U+100-2BA"))
            .map((face) => face.family);
        }"""
    )
    assert "Familjen Grotesk" in loaded


@pytest.mark.parametrize("locale, scoresheet", [("ru", "Бланк"), ("uk", "Бланк")])
def test_a_cyrillic_language_loads_its_font_subsets(page: Page, locale: str, scoresheet: str):
    """Russian and Ukrainian text uses Commissioner and JetBrains Mono's Cyrillic faces.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        locale (str): A Cyrillic locale.
        scoresheet (str): Its name of the Scoresheet menu item.
    """
    page.goto("/")
    page.locator("#locale-picker").select_option(locale)
    expect(page.locator("html")).to_have_attribute("lang", locale)
    expect(page.locator("#tab-scoresheet")).to_have_text(scoresheet)
    loaded = page.evaluate(
        """async () => {
          await document.fonts.load('16px "JetBrains Mono"', "\\u0416");
          await document.fonts.ready;
          return [...document.fonts]
            .filter((face) => face.status === "loaded" && face.unicodeRange.startsWith("U+301,"))
            .map((face) => face.family);
        }"""
    )
    assert "Commissioner" in loaded
    assert "JetBrains Mono" in loaded


def test_switching_language_is_kept_after_a_reload(page: Page):
    """Switching language is kept after a reload.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    expect(page.locator("#openings .opening")).to_have_count(122)
    bird = page.locator('#openings .opening[data-repertoire="bird-opening"] .opening-name').first
    expect(bird).to_have_text("Bird Opening")

    page.locator("#locale-picker").select_option("pt-BR")
    expect(page.locator("html")).to_have_attribute("lang", "pt-BR")
    expect(page.locator("#play")).to_have_text("Jogar")
    expect(page.locator("#selected-total")).to_have_text("Selecionadas: 0")
    expect(page.locator("#tab-new")).to_have_text("Nova partida")
    expect(bird).to_have_text("Abertura Bird")
    # The group stays open, and nothing else changed but the words.
    expect(page.locator("#openings .opening")).to_have_count(122)

    page.reload()
    expect(page.locator("#locale-picker")).to_have_value("pt-BR")
    expect(page.locator("#play")).to_have_text("Jogar")
    expect(bird).to_have_text("Abertura Bird")

    page.locator("#locale-picker").select_option("en-US")
    expect(page.locator("#play")).to_have_text("Play")
    page.reload()
    expect(page.locator("#play")).to_have_text("Play")


def test_switching_mid_game_keeps_the_game(page: Page, seed_prefs):
    """Switching mid game keeps the game.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], color="white", timeControl="10")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)

    page.locator("#locale-picker").select_option("es-419")
    expect(page.locator("#chips .chip").first).to_have_text("Tu turno")
    expect(page.locator("#chips")).to_contain_text("En teoría")
    expect(page.locator("#resign")).to_have_text("Abandonar")
    expect(page.locator("#top-name")).to_have_text("Bot · Calentamiento (800-)")
    expect(page.locator("#bottom-name")).to_have_text("Tú")
    expect(page.locator("#game-card")).to_be_visible()
    expect(page.locator("#movelist .move").first).to_have_text("e4")
    expect(page.locator("#opening-name")).to_have_text("B20 · Defensa Siciliana")
    # The game goes on: the clock was not reset, and the next move is accepted.
    expect(page.locator("#bottom-clock")).not_to_have_text("10:00")
    click_move(page, "d2", "d4")
    wait_for_ply(page, 4)
    expect(page.locator("#chips .chip").first).to_have_text("Tu turno")


def test_opening_names_follow_the_language(page: Page, seed_prefs):
    """Opening names follow the language.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
        seed_prefs (Callable[..., None]): Stores setup preferences before the page loads.
    """
    seed_prefs([ALAPIN], color="white", timeControl="none", locale="pt-BR")
    page.goto("/")
    play(page)
    wait_for_your_move(page, "Sua vez")
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page, "Sua vez")
    click_move(page, "c2", "c3")
    expect(page.locator("#opening-name")).to_have_text("B22 · Defesa Siciliana: Variante Alapin")

    page.locator("#resign").click()
    page.locator("#resign").click()
    expect(page.locator("#end-variation")).to_have_text("B22 · Defesa Siciliana: Variante Alapin")
    page.locator("#locale-picker").select_option("en-US")
    expect(page.locator("#end-variation")).to_have_text("B22 · Sicilian Defense: Alapin Variation")
    expect(page.locator("#opening-name")).to_have_text("B22 · Sicilian Defense: Alapin Variation")

    # Saved games show it in the chosen language, and a search finds it in either.
    page.locator("#locale-picker").select_option("es-419")
    page.locator("#tab-saved").click()
    row = page.locator("#saved-list .saved-game").first
    expect(row).to_contain_text("Defensa Siciliana: Variante Alapin")
    page.locator("#saved-search").fill("variante alapin")
    expect(row).to_contain_text("Defensa Siciliana: Variante Alapin")
    page.locator("#saved-search").fill("alapin variation")
    expect(row).to_contain_text("Defensa Siciliana: Variante Alapin")


def test_a_code_saved_before_the_rename_is_replaced(page: Page):
    """A browser that saved `es` (Latin American Spanish) gets es-419, and the preference with it.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.add_init_script(
        "if (!sessionStorage.getItem('seeded')) {"
        " sessionStorage.setItem('seeded', '1');"
        " localStorage.setItem('chess-trainer.prefs', JSON.stringify({ locale: 'es' }));"
        "}"
    )
    page.goto("/")
    expect(page.locator("#locale-picker")).to_have_value("es-419")
    expect(page.locator("#tab-help")).to_have_text("Ayuda")
    saved = page.evaluate("JSON.parse(localStorage.getItem('chess-trainer.prefs')).locale")
    assert saved == "es-419"
