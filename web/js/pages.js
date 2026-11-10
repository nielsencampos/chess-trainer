// The Help and Scoresheet pages, shown in the board area in place of the board.
// The scoresheet is an unofficial A4 sheet, for training only, printed from the browser.

import { getLocale, localize, t } from "./i18n.js";

const COLUMNS = 4;
const ROWS = 30;
const PAGES = ["help", "sheet"];

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
      const english = `help/en/${name}.webp`;
      if (!image.src.endsWith(english)) image.src = english;
    });
    localize(image, () => {
      image.src = `help/${encodeURIComponent(getLocale())}/${name}.webp`;
      image.alt = t(`help.fig.${name}`);
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
 * @param {string | null} page  `help`, `sheet`, or null for the board.
 * @returns {void}
 */
export function showPage(page) {
  for (const name of PAGES) byId(`${name}-page`).hidden = page !== name;
  /** @type {HTMLElement} */ (document.querySelector(".board-column")).hidden = page !== null;
  document.querySelector(".board-area")?.classList.toggle("showing-page", page !== null);
  if (page === "sheet") fitSheet();
}
