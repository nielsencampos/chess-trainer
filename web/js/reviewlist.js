// Move list of a review: the scoresheet of the main line, with what the PGN says about each
// move (the site's classification icon, a symbol, the time it took), the comments and the side
// variations, which are shown in full rows under the move they branch off.

import { t } from "./i18n.js";
import { moveIcon } from "./icons.js";

/**
 * A move of the review as the server sends it, linked by `linkMoves`.
 * @typedef {{
 *   ply: number, san: string, uci: string, fen: string,
 *   kind?: import("./icons.js").MoveIconKind, symbol?: string, comment?: string,
 *   eval?: {cp: number | null, mate: number | null}, clock_ms?: number, spent_ms?: number,
 *   variations?: ReviewMove[][], book?: boolean, deviation?: boolean,
 *   id: number, main: boolean, prev: ReviewMove | null, next: ReviewMove | null,
 * }} ReviewMove
 */

/**
 * Gives every move an id and links it to the moves before and after it in its own line. The
 * first move of a variation follows the move before the one it replaces.
 * @param {ReviewMove[]} moves  The main line, with variations inside.
 * @returns {ReviewMove[]} Every move, by id.
 */
export function linkMoves(moves) {
  /** @type {ReviewMove[]} */
  const all = [];
  /**
   * Links one line and, inside it, its variations.
   * @param {ReviewMove[]} line  The line's moves.
   * @param {ReviewMove | null} before  The move before the line's first one.
   * @param {boolean} main  Whether it is the main line.
   */
  const link = (line, before, main) => {
    line.forEach((move, index) => {
      move.id = all.length;
      move.main = main;
      move.prev = index === 0 ? before : line[index - 1];
      move.next = line[index + 1] ?? null;
      all.push(move);
      for (const variation of move.variations ?? []) link(variation, move.prev, false);
    });
  };
  link(moves, null, true);
  return all;
}

/**
 * Formats the time a move took.
 * @param {number} ms  Milliseconds.
 * @returns {string} Such as `4.2s`, `35s` or `2:05`.
 */
function formatSpent(ms) {
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  const seconds = Math.round(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * Draws a review's move list: main-line rows, with comments and variations under their move.
 * @param {HTMLElement} container  The list's element.
 * @param {ReviewMove[]} moves  The main line.
 * @param {ReviewMove | null} current  The move on the board, null at the start.
 * @param {boolean} showTheoryMarks  Book and deviation icons, for games played here.
 * @returns {void}
 */
export function renderReviewList(container, moves, current, showTheoryMarks) {
  const fragment = document.createDocumentFragment();
  let index = 0;
  while (index < moves.length) {
    const move = moves[index];
    const number = Math.ceil(move.ply / 2);
    const white = move.ply % 2 === 1 ? move : null;
    const black = white ? moves[index + 1] : move;
    fragment.append(numberCell(`${number}.`));
    if (white && hasExtras(white)) {
      fragment.append(
        mainCell(white, current, showTheoryMarks),
        black ? fillerCell() : emptyCell(),
        extras(white, current),
      );
      if (black) {
        fragment.append(numberCell(`${number}…`), fillerCell(), mainCell(black, current, showTheoryMarks));
        if (hasExtras(black)) fragment.append(extras(black, current));
      }
    } else {
      fragment.append(
        white ? mainCell(white, current, showTheoryMarks) : fillerCell(),
        black ? mainCell(black, current, showTheoryMarks) : emptyCell(),
      );
      if (black && hasExtras(black)) fragment.append(extras(black, current));
    }
    index += white && black ? 2 : 1;
  }
  container.replaceChildren(fragment);
  container.querySelector(".current")?.scrollIntoView({ block: "nearest" });
}

/**
 * Whether a move has a comment or variations, which take a row of their own.
 * @param {ReviewMove} move  The move.
 * @returns {boolean} True if it has any.
 */
function hasExtras(move) {
  return Boolean(move.comment) || (move.variations?.length ?? 0) > 0;
}

/**
 * A move-number cell.
 * @param {string} text  Such as `12.` or `12…`.
 * @returns {HTMLDivElement} The cell.
 */
function numberCell(text) {
  const cell = document.createElement("div");
  cell.className = "number";
  cell.textContent = text;
  return cell;
}

/**
 * An empty move cell, after the last move.
 * @returns {HTMLDivElement} The cell.
 */
function emptyCell() {
  const cell = document.createElement("div");
  cell.className = "move";
  return cell;
}

/**
 * Stands for a move that is written on another row.
 * @returns {HTMLDivElement} The cell.
 */
function fillerCell() {
  const cell = document.createElement("div");
  cell.className = "move filler";
  return cell;
}

/**
 * A main-line move: icon, SAN with its symbol, and the time it took.
 * @param {ReviewMove} move  The move.
 * @param {ReviewMove | null} current  The move on the board.
 * @param {boolean} showTheoryMarks  Whether to mark book moves and deviations.
 * @returns {HTMLDivElement} The cell.
 */
function mainCell(move, current, showTheoryMarks) {
  const cell = document.createElement("div");
  cell.className = "move";
  cell.dataset.node = String(move.id);
  cell.dataset.ply = String(move.ply);
  cell.classList.toggle("current", move === current);
  if (showTheoryMarks) {
    cell.classList.add(move.deviation ? "deviation" : move.book ? "book" : "out");
  }
  const icon = markOf(move, showTheoryMarks);
  if (icon) {
    cell.append(moveIcon(icon, t(`icon.${icon}`)));
    cell.title = t(`icon.${icon}`);
  }
  cell.append(sanOf(move));
  if (move.spent_ms !== undefined) {
    const spent = document.createElement("span");
    spent.className = "spent";
    spent.textContent = formatSpent(move.spent_ms);
    spent.title = t("review.spent");
    cell.append(spent);
  }
  return cell;
}

/**
 * The icon of a move: the site's classification wins; a game played here shows its book marks.
 * @param {ReviewMove} move  The move.
 * @param {boolean} showTheoryMarks  Whether book marks apply.
 * @returns {import("./icons.js").MoveIconKind | null} The icon, or null.
 */
function markOf(move, showTheoryMarks) {
  if (move.kind) return move.kind;
  if (!showTheoryMarks) return null;
  if (move.deviation) return "deviation";
  return move.book ? "book" : null;
}

/**
 * A move's SAN with its position symbol, if any.
 * @param {ReviewMove} move  The move.
 * @returns {HTMLSpanElement} The element.
 */
function sanOf(move) {
  const san = document.createElement("span");
  san.className = "san";
  san.textContent = move.symbol ? `${move.san} ${move.symbol}` : move.san;
  return san;
}

/**
 * The comment of a main-line move and the variations that branch off it, in a full row.
 * @param {ReviewMove} move  The move.
 * @param {ReviewMove | null} current  The move on the board.
 * @returns {HTMLDivElement} The row.
 */
function extras(move, current) {
  const block = document.createElement("div");
  block.className = "move-extras";
  if (move.comment) block.append(comment(move.comment));
  for (const variation of move.variations ?? []) {
    const line = document.createElement("div");
    line.className = "variation";
    appendLine(line, variation, current);
    block.append(line);
  }
  return block;
}

/**
 * A comment.
 * @param {string} text  The comment, without PGN commands.
 * @returns {HTMLSpanElement} The element.
 */
function comment(text) {
  const element = document.createElement("span");
  element.className = "comment";
  element.textContent = text;
  return element;
}

/**
 * A variation as running text: numbers, moves, comments and nested variations in parentheses.
 * @param {HTMLElement} parent  Where to write it.
 * @param {ReviewMove[]} line  The variation's moves.
 * @param {ReviewMove | null} current  The move on the board.
 * @returns {void}
 */
function appendLine(parent, line, current) {
  line.forEach((move, index) => {
    const white = move.ply % 2 === 1;
    if (white || index === 0) {
      const number = document.createElement("span");
      number.className = "variation-number";
      number.textContent = `${Math.ceil(move.ply / 2)}${white ? "." : "…"}`;
      parent.append(number);
    }
    const token = document.createElement("span");
    token.className = "variation-move";
    token.dataset.node = String(move.id);
    token.classList.toggle("current", move === current);
    if (move.kind) {
      token.append(moveIcon(move.kind, t(`icon.${move.kind}`)));
      token.title = t(`icon.${move.kind}`);
    }
    token.append(sanOf(move));
    parent.append(token);
    if (move.comment) parent.append(comment(move.comment));
    for (const nested of move.variations ?? []) {
      const group = document.createElement("span");
      group.className = "variation-nested";
      appendLine(group, nested, current);
      parent.append(group);
    }
  });
}
