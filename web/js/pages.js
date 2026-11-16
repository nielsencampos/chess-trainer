// The Help, About and Scoresheet pages, shown in the board area in place of the board.
// The scoresheet is an unofficial A4 sheet, for training only, printed from the browser.

import { DEFAULT_LOCALE, getLocale, localize, t } from "./i18n.js";

const COLUMNS = 4;
const ROWS = 30;
const PAGES = ["help", "about", "sheet"];

/**
 * Finds an element by id.
 * @param {string} id  The element's id.
 * @returns {any} The element.
 */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/**
 * Points each Help picture at its language's file (from scripts/help_media.py), falling back to
 * English, and keeps it and its description following the language.
 * Call it once the first language is loaded.
 * @returns {void}
 */
export function localizeHelpImages() {
  for (const image of document.querySelectorAll("img[data-help-img]")) {
    const name = image.getAttribute("data-help-img");
    image.addEventListener("error", () => {
      const english = `help/${DEFAULT_LOCALE}/${name}.webp`;
      if (!image.src.endsWith(english)) image.src = english;
    });
    localize(image, () => {
      image.src = `help/${encodeURIComponent(getLocale())}/${name}.webp`;
      image.alt = t(`help.fig.${name}`);
    });
  }
}

/** Wikipedias with language variants, opened at the variant of the locale (`zh-cn`). */
const VARIANT_WIKIPEDIAS = new Set(["zh"]);

/**
 * Points each Wikipedia link of the About page at the article in the chosen language, falling
 * back to English and then to the other languages that have one, and keeps it following the
 * language. Each link has a `data-wiki-<lang>` title per Wikipedia that has the article, English
 * always. The link shows the article's address without the scheme.
 * @returns {void}
 */
export function localizeWikiLinks() {
  for (const link of document.querySelectorAll("a[data-wiki-en]")) {
    const anchor = /** @type {HTMLAnchorElement} */ (link);
    /** @type {Record<string, string>} */
    const titles = {};
    for (const [key, title] of Object.entries(anchor.dataset)) {
      if (key.startsWith("wiki") && title) titles[key.slice(4).toLowerCase()] = title;
    }
    localize(anchor, () => {
      const wanted = getLocale().split("-")[0].toLowerCase();
      const lang = [wanted, "en", ...Object.keys(titles)].find((code) => titles[code]) ?? "en";
      // A Wikipedia that writes its language in more than one way (zh: Traditional and
      // Simplified) shows the article in the locale's variant at its own path, as the
      // registry's `wikipedia_variant` says for the opening names (zh.wikipedia.org/zh-cn/…).
      const variant =
        VARIANT_WIKIPEDIAS.has(lang) && lang === wanted ? getLocale().toLowerCase() : "wiki";
      const path = `${lang}.wikipedia.org/${variant}/${(titles[lang] ?? "").replaceAll(" ", "_")}`;
      anchor.href = `https://${encodeURI(path)}`;
      anchor.textContent = path;
    });
  }
}

/**
 * Builds one column of the move table: a header row and `ROWS` numbered rows.
 * @param {number} first  The number of the column's first move.
 * @returns {HTMLTableElement} The column.
 */
function moveColumn(first) {
  const table = document.createElement("table");
  const head = table.createTHead().insertRow();
  for (const key of ["sheet.no", "sheet.white", "sheet.black"]) {
    const cell = document.createElement("th");
    cell.dataset.i18n = key;
    head.append(cell);
  }
  const body = table.createTBody();
  for (let move = first; move < first + ROWS; move += 1) {
    const row = body.insertRow();
    row.insertCell().textContent = String(move);
    row.insertCell();
    row.insertCell();
  }
  return table;
}

/**
 * Scales the A4 sheet down to the width of the board area, so it shows whole on screen.
 * Printing ignores the scale.
 * @returns {void}
 */
function fitSheet() {
  const frame = byId("sheet-frame");
  const sheet = frame.firstElementChild;
  const scale = Math.min(1, frame.clientWidth / sheet.offsetWidth);
  frame.style.setProperty("--sheet-scale", String(scale));
  frame.style.height = `${sheet.offsetHeight * scale}px`;
}

/**
 * Draws the scoresheet's move table and wires its print button.
 * Call it before the page is translated, so the table headers are translated too.
 * @returns {void}
 */
export function initPages() {
  const moves = byId("sheet-moves");
  for (let column = 0; column < COLUMNS; column += 1) moves.append(moveColumn(1 + column * ROWS));
  byId("sheet-print").addEventListener("click", () => window.print());
  new ResizeObserver(() => {
    if (!byId("sheet-page").hidden) fitSheet();
  }).observe(byId("sheet-page"));
}

/**
 * Shows a page in the board area in place of the board, or the board again.
 * @param {string | null} page  `help`, `about`, `sheet`, or null for the board.
 * @returns {void}
 */
export function showPage(page) {
  for (const name of PAGES) byId(`${name}-page`).hidden = page !== name;
  /** @type {HTMLElement} */ (document.querySelector(".board-column")).hidden = page !== null;
  document.querySelector(".board-area")?.classList.toggle("showing-page", page !== null);
  if (page === "sheet") fitSheet();
}
