// Move notation on screen (#53): figurines, English letters or the UI language's letters.
// Moves are stored, sent and exported in English SAN; this module only changes how they are
// drawn. Only the piece letter changes: squares, x, +, #, = and O-O stay as they are.

import { refresh, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

/** @typedef {"local" | "english" | "figurines"} Notation */

/** The notations, in the picker's order; the quick switch cycles through them in this order. */
export const NOTATIONS = /** @type {Notation[]} */ (["local", "english", "figurines"]);
/** The notation of a browser that has not chosen one. */
export const DEFAULT_NOTATION = /** @type {Notation} */ ("figurines");
/** The English SAN letters, in the order of the `notation.pieces` key. */
const PIECES = ["K", "Q", "R", "B", "N", "P"];
// A piece letter: the first one of a piece move, or the one after "=" of a promotion.
const PIECE_LETTER = /^[KQRBN]|(?<==)[QRBN]/g;

/** @type {Notation} */
let notation = readNotation();

/**
 * The stored notation, or the default when none is stored or it is not a known one.
 * @returns {Notation} The notation.
 */
function readNotation() {
  const stored = getPref("notation", DEFAULT_NOTATION);
  return NOTATIONS.includes(stored) ? stored : DEFAULT_NOTATION;
}

/**
 * The notation in use.
 * @returns {Notation} The notation.
 */
export function getNotation() {
  return notation;
}

/**
 * Switches the notation, keeps it in this browser and draws every move on screen again.
 * @param {Notation} chosen  The notation.
 * @returns {void}
 */
export function setNotation(chosen) {
  if (!NOTATIONS.includes(chosen) || chosen === notation) return;
  notation = chosen;
  setPref("notation", chosen);
  document.documentElement.dataset.notation = chosen;
  refresh();
}

/**
 * The notation after this one, for the quick switch.
 * @param {Notation} [from]  The notation; the one in use by default.
 * @returns {Notation} The next one, back to the first after the last.
 */
export function nextNotation(from = notation) {
  return NOTATIONS[(NOTATIONS.indexOf(from) + 1) % NOTATIONS.length];
}

/**
 * The UI language's letter for each English piece letter, from its glossary (brief §8).
 * @returns {Record<string, string>} English letter -> local letter; English when it has none.
 */
function localLetters() {
  const letters = t("notation.pieces").split(/\s+/);
  const valid = letters.length === PIECES.length && letters.every(Boolean);
  return Object.fromEntries(PIECES.map((piece, index) => [piece, valid ? letters[index] : piece]));
}

/**
 * A move as text in the UI language's letters, for search and other plain text.
 * @param {string} san  The move in English SAN.
 * @returns {string} The move with the language's piece letters.
 */
export function localSan(san) {
  const letters = localLetters();
  return san.replace(PIECE_LETTER, (piece) => letters[piece]);
}

/**
 * A move as plain text in a notation, where a picture cannot go (a select's options). Plain
 * text has no figurines, so figurines fall back to English letters.
 * @param {string} san  The move in English SAN.
 * @param {Notation} [shown]  The notation; the one in use by default.
 * @returns {string} The text.
 */
export function sanText(san, shown = notation) {
  return shown === "local" ? localSan(san) : san;
}

/**
 * One figurine: the Merida piece as a picture, with the English letter as its text, so copying
 * the move gives readable SAN. The letter is transparent on screen.
 * @param {string} piece  The English letter (K, Q, R, B, N).
 * @returns {HTMLSpanElement} The figurine.
 */
function figurine(piece) {
  const element = document.createElement("span");
  element.className = `figurine figurine-${piece}`;
  element.textContent = piece;
  return element;
}

/**
 * A move drawn in a notation, isolated from the text around it (as SAN, in any direction).
 * @param {string} san  The move in English SAN.
 * @param {Notation} [shown]  The notation; the one in use by default.
 * @returns {HTMLSpanElement} The move, with `data-san` holding its English SAN.
 */
export function sanElement(san, shown = notation) {
  const element = document.createElement("span");
  element.className = "notation";
  element.dir = "ltr";
  element.dataset.san = san;
  // In the move list's mono font the letter O looks like a zero, so castling takes the UI font.
  const castle = /^O-O(?:-O)?/.exec(san);
  if (castle) {
    const letters = document.createElement("span");
    letters.className = "castle";
    letters.textContent = castle[0];
    element.append(letters, san.slice(castle[0].length));
    return element;
  }
  if (shown !== "figurines") {
    element.textContent = sanText(san, shown);
    return element;
  }
  let last = 0;
  for (const match of san.matchAll(PIECE_LETTER)) {
    const index = match.index ?? 0;
    if (index > last) element.append(san.slice(last, index));
    element.append(figurine(match[0]));
    last = index + match[0].length;
  }
  if (last < san.length) element.append(san.slice(last));
  return element;
}

/**
 * The moves of a book line, `1.e4 e5 2.Nf3`, drawn in a notation, numbers as they are.
 * @param {string} pgn  The line's moves, in English SAN with move numbers.
 * @returns {DocumentFragment} The moves.
 */
export function lineElement(pgn) {
  const fragment = document.createDocumentFragment();
  pgn.split(" ").forEach((token, index) => {
    if (index > 0) fragment.append(" ");
    const [, number, san] = /^(\d+\.(?:\.\.)?)?(.*)$/.exec(token) ?? [];
    if (number) fragment.append(number);
    if (san) fragment.append(sanElement(san));
  });
  return fragment;
}

/**
 * The moves of a book line in the UI language's letters, for search.
 * @param {string} pgn  The line's moves, in English SAN with move numbers.
 * @returns {string} The same text with the language's piece letters.
 */
export function localLine(pgn) {
  return pgn
    .split(" ")
    .map((token) => token.replace(/^(\d+\.(?:\.\.)?)?(.*)$/, (_, number, san) => (number ?? "") + localSan(san)))
    .join(" ");
}

/**
 * The name of a notation in the UI language.
 * @param {Notation} name  The notation.
 * @returns {string} Its name, as in the picker.
 */
export function notationName(name) {
  return t(`notation.${name}`);
}

/** The floating tip that shows a move in the other two notations. */
let tip = /** @type {HTMLDivElement | null} */ (null);

/**
 * Shows a move's other two notations next to it.
 * @param {HTMLElement} move  The `.notation` element, or an element holding one.
 * @returns {void}
 */
function showTip(move) {
  const shown = move.matches(".notation") ? move : move.querySelector(".notation");
  const san = /** @type {HTMLElement | null} */ (shown)?.dataset.san;
  if (!san) return;
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "notation-tip";
    tip.setAttribute("role", "tooltip");
    document.body.append(tip);
  }
  // In English, local and English letters are the same: show that once.
  const others = NOTATIONS.filter((name) => name !== notation).filter(
    (name, index, list) => index === 0 || name === "figurines" || sanText(san, name) !== sanText(san, list[0]),
  );
  tip.replaceChildren();
  others.forEach((name, index) => {
    if (index > 0) tip?.append(" · ");
    tip?.append(sanElement(san, name));
  });
  tip.hidden = false;
  const box = move.getBoundingClientRect();
  const width = tip.offsetWidth;
  const left = Math.min(Math.max(4, box.left + box.width / 2 - width / 2), innerWidth - width - 4);
  const above = box.top - tip.offsetHeight - 6;
  // The rectangle is in screen coordinates; the start side is the right one in RTL pages.
  const rtl = getComputedStyle(document.documentElement).direction === "rtl";
  tip.style.insetInlineStart = `${rtl ? innerWidth - left - width : left}px`;
  tip.style.top = `${above >= 4 ? above : box.bottom + 6}px`;
}

/** Hides the tip. */
function hideTip() {
  if (tip) tip.hidden = true;
}

/**
 * Shows the other two notations of a move on hover and on keyboard focus, anywhere on the page.
 * Hover is on the move itself, so an icon beside it keeps its own tooltip.
 * @returns {void}
 */
export function initNotation() {
  document.documentElement.dataset.notation = notation;
  document.addEventListener("mouseover", (event) => {
    const move = /** @type {HTMLElement} */ (event.target).closest?.("[data-tip] .notation");
    if (move) showTip(/** @type {HTMLElement} */ (move));
  });
  document.addEventListener("mouseout", (event) => {
    if (/** @type {HTMLElement} */ (event.target).closest?.("[data-tip] .notation")) hideTip();
  });
  document.addEventListener("focusin", (event) => {
    const target = /** @type {HTMLElement} */ (event.target);
    if (target.matches?.("[data-tip]") && target.querySelector(".notation")) showTip(target);
  });
  document.addEventListener("focusout", hideTip);
  document.addEventListener("scroll", hideTip, true);
}
