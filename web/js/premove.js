// Where a piece could go by shape alone. The position will have changed by the time a premove
// plays, so blockers are ignored here and legality is checked when it is played.

const FILES = "abcdefgh";
const ROOK_RAYS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
const BISHOP_RAYS = [[1, 1], [1, -1], [-1, 1], [-1, -1]];
const KNIGHT_JUMPS = [[1, 2], [2, 1], [2, -1], [1, -2], [-1, -2], [-2, -1], [-2, 1], [-1, 2]];

/**
 * The squares a piece could premove to, by its shape alone.
 * @param {string} square  The piece's square, such as `e2`.
 * @param {{color: "w" | "b", type: string}} piece  The piece.
 * @param {boolean} [chess960]  The king can castle from any square, to anywhere on its rank.
 * @returns {string[]} The target squares.
 */
export function premoveDestinations(square, piece, chess960 = false) {
  const file = FILES.indexOf(square[0]);
  const rank = Number(square[1]);
  /** @type {string[]} */
  const targets = [];
  /**
   * Adds the square at an offset, if it is on the board.
   * @param {number} df  Files to the right.
   * @param {number} dr  Ranks up.
   */
  const add = (df, dr) => {
    const nextFile = file + df;
    const nextRank = rank + dr;
    if (nextFile >= 0 && nextFile < 8 && nextRank >= 1 && nextRank <= 8) {
      targets.push(`${FILES[nextFile]}${nextRank}`);
    }
  };
  /**
   * Adds every square along some rays, ignoring blockers.
   * @param {number[][]} rays  The [file, rank] directions.
   */
  const slide = (rays) => {
    for (const [df, dr] of rays) {
      for (let step = 1; step < 8; step += 1) add(df * step, dr * step);
    }
  };

  switch (piece.type) {
    case "p": {
      const forward = piece.color === "w" ? 1 : -1;
      add(0, forward);
      if (rank === (piece.color === "w" ? 2 : 7)) add(0, 2 * forward);
      add(-1, forward);
      add(1, forward);
      break;
    }
    case "n":
      for (const [df, dr] of KNIGHT_JUMPS) add(df, dr);
      break;
    case "b":
      slide(BISHOP_RAYS);
      break;
    case "r":
      slide(ROOK_RAYS);
      break;
    case "q":
      slide(ROOK_RAYS);
      slide(BISHOP_RAYS);
      break;
    case "k":
      for (const [df, dr] of [...ROOK_RAYS, ...BISHOP_RAYS]) add(df, dr);
      if (chess960 && rank === (piece.color === "w" ? 1 : 8)) {
        for (let df = -file; df < 8 - file; df += 1) {
          if (Math.abs(df) > 1) add(df, 0);
        }
      } else if (square === (piece.color === "w" ? "e1" : "e8")) {
        add(-2, 0);
        add(2, 0);
      }
      break;
    default:
      break;
  }
  return targets;
}
