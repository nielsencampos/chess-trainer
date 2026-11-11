"""Help and Scoresheet (brief §4): pages in the board area, in place of the board."""

import re

from playwright.sync_api import Page, expect


def test_help_replaces_the_board_with_the_notices_first(page: Page):
    """Help shows in the board area, with the fair-play and evaluation notices first.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator("#tab-help").click()
    expect(page.locator("#tab-help")).to_have_class("tab active")
    expect(page.locator("#help-page")).to_be_visible()
    expect(page.locator(".board-column")).to_be_hidden()
    expect(page.locator("#setup-card")).to_be_hidden()
    notices = page.locator("#help-page .notice strong")
    expect(notices).to_have_text(["Never use it to cheat", "The evaluation here is basic"])
    expect(page.locator("#help-page .help-section")).to_have_count(8)
    pictures = page.locator("#help-page img[data-help-img]")
    expect(pictures).to_have_count(5)
    for index in range(5):
        expect(pictures.nth(index)).to_have_attribute("src", re.compile(r"^help/en/\w+\.webp$"))
        pictures.nth(index).scroll_into_view_if_needed()
        expect(pictures.nth(index)).to_have_js_property("complete", True)
        assert pictures.nth(index).evaluate("(image) => image.naturalWidth") > 0

    page.locator("#tab-new").click()
    expect(page.locator("#help-page")).to_be_hidden()
    expect(page.locator(".board-column")).to_be_visible()


def test_help_has_the_training_advice(page: Page):
    """How to train lists its five pieces of advice, with numbered steps for each side's move.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator("#tab-help").click()
    section = page.locator("#help-page .help-section", has_text="How to train")
    expect(section.locator("h3")).to_have_count(5)
    expect(section.locator("ol li")).to_have_count(7)


def test_about_is_a_page_after_help_in_the_chosen_language(page: Page):
    """About follows Help in the menu, shows in the board area, and its links open a new tab.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    tabs = page.locator("#sidebar-tabs .tab")
    expect(tabs.nth(-2)).to_have_id("tab-help")
    expect(tabs.last).to_have_id("tab-about")
    page.locator("#locale-picker").select_option("pt-BR")
    page.locator("#tab-about").click()
    expect(page.locator("#tab-about")).to_have_class("tab active")
    expect(page.locator("#about-page")).to_be_visible()
    expect(page.locator(".board-column")).to_be_hidden()
    expect(page.locator("#about-page h2")).to_have_text("Sobre o Chess Trainer")
    tal = page.locator("#about-page a[data-wiki-pt='Mikhail Tal']")
    expect(tal).to_have_attribute("href", "https://pt.wikipedia.org/wiki/Mikhail_Tal")
    page.locator("#locale-picker").select_option("es")
    expect(tal).to_have_attribute("href", "https://es.wikipedia.org/wiki/Mija%C3%ADl_Tal")
    expect(tal).to_have_text("es.wikipedia.org/wiki/Mijaíl_Tal")
    rosen = page.locator("#about-page a[data-wiki-en^='Eric Rosen']")
    expect(rosen).to_have_attribute(
        "href", "https://en.wikipedia.org/wiki/Eric_Rosen_(chess_player)"
    )
    page.locator("#locale-picker").select_option("pt-BR")
    expect(page.locator("#about-page .about-path > li")).to_have_count(9)
    expect(page.locator("#about-page .about-legends > li")).to_have_count(18)
    expect(page.locator("#about-page .about-thanks > li")).to_have_count(5)
    expect(page.locator("#about-page a[href='https://github.com/niklasf']")).to_be_visible()
    links = page.locator("#about-page a")
    for index in range(links.count()):
        expect(links.nth(index)).to_have_attribute("target", "_blank")
        expect(links.nth(index)).to_have_attribute("rel", "noopener noreferrer")

    page.locator("#tab-help").click()
    expect(page.locator("#about-page")).to_be_hidden()
    expect(page.locator("#help-page")).to_be_visible()


def test_scoresheet_follows_the_language_and_fits_the_area(page: Page):
    """The sheet has 120 numbered moves and the disclaimer, in the chosen language, scaled to fit.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    page.goto("/")
    page.locator("#locale-picker").select_option("pt-BR")
    page.locator("#tab-scoresheet").click()
    expect(page.locator(".board-column")).to_be_hidden()
    sheet = page.locator("#sheet-page .sheet")
    expect(sheet.locator("h1")).to_have_text("Planilha de anotação de xadrez")
    expect(sheet.locator(".sheet-disclaimer")).to_have_text(
        "Planilha não oficial · Apenas para treino"
    )
    rows = sheet.locator("#sheet-moves tbody tr")
    expect(rows).to_have_count(120)
    expect(rows.last.locator("td").first).to_have_text("120")
    sheet_box = sheet.bounding_box()
    frame_box = page.locator("#sheet-frame").bounding_box()
    assert sheet_box and frame_box
    assert sheet_box["width"] <= frame_box["width"] + 1
