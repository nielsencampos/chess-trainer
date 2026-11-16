// Move list in scoresheet style: numbered rows, white and black columns. The text is never
// colored: a book move and a deviation are marked with an icon.

import { t } from "./i18n.js";
import { moveIcon } from "./icons.js";
import { sanElement } from "./notation.js";

/**
 * @typedef {{san: string, uci?: string, outOfTheory: boolean, deviation: boolean,
 *   botDeviation?: boolean}} PlyView
 */

/**
 * Draws the move list.
 * @param {HTMLElement} container  The list's element.
 * @param {PlyView[]} plies  The moves, in order.
 * @param {boolean} showTheoryMarks  False hides marks while the out-of-theory warning is off.
 * @returns {void}
 */
export function renderMoveList(container, plies, showTheoryMarks) {
  const fragment = document.createDocumentFragment();
  for (let index = 0; index < plies.length; index += 2) {
    const number = document.createElement("div");
    number.className = "number";
    number.textContent = `${index / 2 + 1}.`;
    // "12." keeps its dot after the number in a right-to-left language too (#37).
    number.dir = "ltr";
    fragment.append(
      number,
      moveCell(plies[index], showTheoryMarks),
      moveCell(plies[index + 1], showTheoryMarks),
    );
  }
  container.replaceChildren(fragment);
  container.scrollTop = container.scrollHeight;
}

/**
 * Draws one move of the list.
 * @param {PlyView | undefined} ply  The move, or undefined for an empty cell.
 * @param {boolean} showTheoryMarks  Whether to mark book moves and deviations.
 * @returns {HTMLDivElement} The cell.
 */
function moveCell(ply, showTheoryMarks) {
  const cell = document.createElement("div");
  cell.className = "move";
  if (!ply) return cell;
  const san = document.createElement("span");
  san.className = "san";
  san.append(sanElement(ply.san));
  cell.append(san);
  // Keyboard focus shows the move in the other notations, as hover does.
  cell.tabIndex = 0;
  cell.dataset.tip = "";
  if (showTheoryMarks) {
    if (ply.deviation || ply.botDeviation) {
      const title = t(ply.deviation ? "icon.deviation" : "icon.botDeviation");
      cell.classList.add("deviation");
      cell.prepend(moveIcon("deviation", title));
    } else if (ply.outOfTheory) {
      cell.classList.add("out");
    } else {
      cell.classList.add("book");
      cell.prepend(moveIcon("book", t("icon.book")));
    }
  }
  return cell;
}
