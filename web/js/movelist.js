// Move list in scoresheet style: numbered rows, white and black columns.

/**
 * @typedef {{san: string, outOfTheory: boolean, deviation: boolean}} PlyView
 */

/**
 * @param {HTMLElement} container
 * @param {PlyView[]} plies
 * @param {boolean} showTheoryMarks  False hides marks while the out-of-theory warning is off.
 */
export function renderMoveList(container, plies, showTheoryMarks) {
  const fragment = document.createDocumentFragment();
  for (let index = 0; index < plies.length; index += 2) {
    const number = document.createElement("div");
    number.className = "number";
    number.textContent = `${index / 2 + 1}.`;
    fragment.append(number, moveCell(plies[index], showTheoryMarks), moveCell(plies[index + 1], showTheoryMarks));
  }
  container.replaceChildren(fragment);
  container.scrollTop = container.scrollHeight;
}

/**
 * @param {PlyView | undefined} ply
 * @param {boolean} showTheoryMarks
 */
function moveCell(ply, showTheoryMarks) {
  const cell = document.createElement("div");
  cell.className = "move";
  if (!ply) return cell;
  cell.textContent = ply.san;
  if (showTheoryMarks) {
    if (ply.deviation) cell.classList.add("deviation");
    else if (ply.outOfTheory) cell.classList.add("out");
  }
  return cell;
}
