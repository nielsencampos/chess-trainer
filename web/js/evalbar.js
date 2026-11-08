// Evaluation bar to the left of the board: Stockfish at full strength, from White's side.

import { api } from "./api.js";

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

const DEBOUNCE_MS = 120;

/**
 * White's chance to win, 0 to 1, from centipawns: the curve Lichess publishes.
 * @param {number} cp
 */
function whiteShare(cp) {
  return 1 / (1 + Math.exp(-0.00368208 * cp));
}

/**
 * @param {{cp: number | null, mate: number | null}} score
 * @returns {{share: number, label: string, whiteAhead: boolean}}
 */
export function describe(score) {
  if (score.mate !== null) {
    // Mate 0 is a finished game; the server then gives the winner's side in cp.
    const whiteAhead = score.mate === 0 ? (score.cp ?? 0) > 0 : score.mate > 0;
    return {
      share: whiteAhead ? 1 : 0,
      label: score.mate === 0 ? "#" : `M${Math.abs(score.mate)}`,
      whiteAhead,
    };
  }
  const cp = score.cp ?? 0;
  const pawns = Math.abs(cp) / 100;
  return {
    share: whiteShare(cp),
    label: pawns >= 10 ? pawns.toFixed(0) : pawns.toFixed(1),
    whiteAhead: cp >= 0,
  };
}

export class EvalBar {
  constructor() {
    this.element = byId("eval-bar");
    this.sequence = 0;
    this.timer = 0;
    // One request at a time: the engine searches one position at a time, and a second each, so
    // moving fast through a game must not queue every position passed on the way.
    this.inFlight = false;
    /** @type {{fen: string, chess960: boolean, sequence: number} | null} */
    this.next = null;
  }

  /**
   * @param {string} fen
   * @param {boolean} chess960
   * @param {"w" | "b"} orientation  The color at the bottom of the board.
   * @param {{cp: number | null, mate: number | null}} [known]  The evaluation the PGN gives
   *   for this position (Lichess's analysis): shown at once, with no engine request.
   */
  show(fen, chess960, orientation, known) {
    this.sequence += 1;
    const sequence = this.sequence;
    this.element.hidden = false;
    this.element.classList.toggle("flipped", orientation === "b");
    clearTimeout(this.timer);
    if (known) {
      this.render(known);
      return;
    }
    this.timer = setTimeout(() => {
      this.next = { fen, chess960, sequence };
      void this.request();
    }, DEBOUNCE_MS);
  }

  async request() {
    if (this.inFlight || this.next === null) return;
    const { fen, chess960, sequence } = this.next;
    this.next = null;
    this.inFlight = true;
    try {
      const score = await api.evaluate(fen, chess960);
      if (sequence === this.sequence) this.render(score);
    } catch (error) {
      console.error(error);
      if (sequence === this.sequence) this.hide();
    } finally {
      this.inFlight = false;
    }
    void this.request(); // The position on screen now, if it changed meanwhile.
  }

  /** @param {{cp: number | null, mate: number | null}} score */
  render(score) {
    const { share, label, whiteAhead } = describe(score);
    byId("eval-fill").style.height = `${(share * 100).toFixed(1)}%`;
    const text = byId("eval-label");
    text.textContent = label;
    this.element.dataset.cp = String(score.cp ?? "");
    this.element.dataset.mate = String(score.mate ?? "");
    // The number sits at the end of the side that is ahead.
    const whiteAtBottom = !this.element.classList.contains("flipped");
    const atBottom = whiteAhead === whiteAtBottom;
    text.classList.toggle("bottom", atBottom);
    text.classList.toggle("top", !atBottom);
    text.style.color = whiteAhead ? "#3a3a3a" : "#f2f2f2";
  }

  hide() {
    this.sequence += 1;
    this.next = null;
    clearTimeout(this.timer);
    this.element.hidden = true;
  }
}
