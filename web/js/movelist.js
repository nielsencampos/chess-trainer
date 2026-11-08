// Move list in scoresheet style: numbered rows, white and black columns. The text is never
// colored: a book move and a deviation are marked with an icon.

import { t } from "./i18n.js";
import { moveIcon } from "./icons.js";

/**
 * @typedef {{san: string, uci?: string, outOfTheory: boolean, deviation: boolean}} PlyView
 */

/**
 * @param {HTMLElement} container
 * @param {PlyView[]} plies
 * @param {boolean} showTheoryMarks  False hides marks while the out-of-theory warning is off.
 * @param {number} [currentPly]  In a review, the move being shown.
 */
export function renderMoveList(container, plies, showTheoryMarks, currentPly) {
  const fragment = document.createDocumentFragment();
  for (let index = 0; index < plies.length; index += 2) {
    const number = document.createElement("div");
    number.className = "number";
    number.textContent = `${index / 2 + 1}.`;
    fragment.append(
      number,
      moveCell(plies[index], showTheoryMarks, index + 1, currentPly),
      moveCell(plies[index + 1], showTheoryMarks, index + 2, currentPly),
    );
  }
  container.replaceChildren(fragment);
  if (currentPly === undefined) container.scrollTop = container.scrollHeight;
  else container.querySelector(".current")?.scrollIntoView({ block: "nearest" });
}

/**
 * @param {PlyView | undefined} ply
 * @param {boolean} showTheoryMarks
 * @param {number} number
 * @param {number} [currentPly]
 */
function moveCell(ply, showTheoryMarks, number, currentPly) {
  const cell = document.createElement("div");
  cell.className = "move";
  if (!ply) return cell;
  const san = document.createElement("span");
  san.className = "san";
  san.textContent = ply.san;
  cell.append(san);
  if (currentPly !== undefined) {
    cell.dataset.ply = String(number);
    cell.classList.toggle("current", number === currentPly);
  }
  if (showTheoryMarks) {
    if (ply.deviation) {
      cell.classList.add("deviation");
      cell.prepend(moveIcon("deviation", t("icon.deviation")));
      cell.title = t("icon.deviation");
    } else if (ply.outOfTheory) {
      cell.classList.add("out");
    } else {
      cell.classList.add("book");
      cell.prepend(moveIcon("book", t("icon.book")));
      cell.title = t("icon.book");
    }
  }
  return cell;
}
