"""Language picker (brief §8): switching redraws the page in place and is kept after a reload."""

from playwright.sync_api import Page, expect

from tests.e2e.conftest import click_move, play, wait_for_ply, wait_for_your_move

ALAPIN = "1. e4 c5 2. c3"


def test_picker_lists_each_language_in_its_own_name(page: Page):
    page.goto("/")
    options = page.locator("#locale-picker option")
    expect(options).to_have_text(["English", "Español", "Português (Brasil)"])
    expect(page.locator("#locale-picker")).to_have_value("en")


def test_switching_language_is_kept_after_a_reload(page: Page):
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

    page.locator("#locale-picker").select_option("en")
    expect(page.locator("#play")).to_have_text("Play")
    page.reload()
    expect(page.locator("#play")).to_have_text("Play")


def test_switching_mid_game_keeps_the_game(page: Page, seed_prefs):
    seed_prefs([ALAPIN], color="white", timeControl="10")
    page.goto("/")
    play(page)
    wait_for_your_move(page)
    click_move(page, "e2", "e4")
    wait_for_ply(page, 2)
    wait_for_your_move(page)

    page.locator("#locale-picker").select_option("es")
    expect(page.locator("#chips .chip").first).to_have_text("Tu turno")
    expect(page.locator("#chips")).to_contain_text("En teoría")
    expect(page.locator("#resign")).to_have_text("Abandonar")
    expect(page.locator("#top-name")).to_have_text("Bot · Calentamiento")
    expect(page.locator("#bottom-name")).to_have_text("Tú")
    expect(page.locator("#game-card")).to_be_visible()
    expect(page.locator("#movelist .move").first).to_have_text("e4")
    # The game goes on: the clock was not reset, and the next move is accepted.
    expect(page.locator("#bottom-clock")).not_to_have_text("10:00")
    click_move(page, "d2", "d4")
    wait_for_ply(page, 4)
    expect(page.locator("#chips .chip").first).to_have_text("Tu turno")
