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
