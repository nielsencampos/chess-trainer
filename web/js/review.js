// Read-only review of a saved game or a book line: arrows, keys, and clicking on a move.

import { api } from "./api.js";
import { t } from "./i18n.js";
import { EvalBar } from "./evalbar.js";
import { formatClock } from "./clock.js";
import { linkMoves, renderReviewList } from "./reviewlist.js";

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

const FIRST = 0;

export class Review {
  /**
   * @param {import("./board.js").Board} board
   * @param {() => void} onClose
   * @param {(gameId: string, ply: number) => void} onPlayFromHere
   */
  constructor(board, onClose, onPlayFromHere) {
    this.board = board;
    this.onClose = onClose;
    this.onPlayFromHere = onPlayFromHere;
    this.active = false;
    /** @type {any} */
    this.data = null;
    /** @type {string | null} */
    this.gameId = null;
    this.ply = FIRST;
    /** @type {import("./reviewlist.js").ReviewMove | null} The move on the board. */
    this.node = null;
    /** @type {import("./reviewlist.js").ReviewMove[]} */
    this.nodes = [];
    this.flipped = false;
    this.hasClocks = false;
    this.evalBar = new EvalBar();

    byId("review-first").addEventListener("click", () => this.goTo(FIRST));
    byId("review-prev").addEventListener("click", () => this.back());
    byId("review-next").addEventListener("click", () => this.forward());
    byId("review-last").addEventListener("click", () => this.goTo(this.lastPly));
    byId("review-flip").addEventListener("click", () => this.flip());
    byId("review-close").addEventListener("click", () => this.close());
    byId("review-play").addEventListener("click", () => {
      if (this.gameId === null) return;
      const { gameId, ply } = this;
      this.close();
      this.onPlayFromHere(gameId, ply);
    });
    byId("movelist").addEventListener("click", (/** @type {any} */ event) => {
      if (!this.active) return;
      const cell = event.target.closest?.("[data-node]");
      if (cell) this.select(this.nodes[Number(cell.dataset.node)] ?? null);
    });
    document.addEventListener("keydown", (event) => this.onKey(event));
  }

  get lastPly() {
    return this.data ? this.data.moves.length : FIRST;
  }

  /** @param {string} gameId */
  async openGame(gameId) {
    this.show(await api.reviewGame(gameId), gameId);
  }

  /** @param {string} variantId */
  async openLine(variantId) {
    this.show(await api.reviewLine(variantId), null);
  }

  /**
   * @param {any} data
   * @param {string | null} gameId
   */
  show(data, gameId) {
    this.active = true;
    this.data = data;
    this.gameId = gameId;
    this.nodes = linkMoves(data.moves);
    this.flipped = false;
    byId("review-bar").hidden = false;
    byId("review-play").hidden = gameId === null || data.chess960 === true;
    this.hasClocks = data.moves.some((/** @type {any} */ move) => move.clock_ms !== undefined);
    for (const id of ["top-clock", "bottom-clock"]) {
      byId(id).className = "clock"; // Read-only: no side to move, no low-time color.
      byId(id).hidden = !this.hasClocks;
    }
    byId("movelist").hidden = false;
    byId("chips").replaceChildren();
    byId("opening-name").textContent = data.opening
      ? t("moves.openingName", { eco: data.eco ?? "", name: data.opening })
      : t("moves.noOpening");
    this.board.setMovable(null);
    this.board.setOrientation("w");
    this.renderNames();
    this.goTo(this.lastPly);
  }

  renderNames() {
    const white = this.data.white ?? t("setup.white");
    const black = this.data.black ?? t("setup.black");
    byId("bottom-name").textContent = this.flipped ? black : white;
    byId("top-name").textContent = this.flipped ? white : black;
  }

  flip() {
    this.flipped = !this.flipped;
    this.board.setOrientation(this.flipped ? "b" : "w");
    this.renderNames();
    this.select(this.node);
  }

  /** @param {number} ply A move of the main line, 0 for the start. */
  goTo(ply) {
    if (!this.active) return;
    const clamped = Math.min(this.lastPly, Math.max(FIRST, ply));
    this.select(clamped === FIRST ? null : this.data.moves[clamped - 1]);
  }

  back() {
    if (this.node) this.select(this.node.prev);
  }

  forward() {
    const next = this.node ? this.node.next : (this.data?.moves[0] ?? null);
    if (next) this.select(next);
  }

  /** @param {import("./reviewlist.js").ReviewMove | null} node */
  select(node) {
    if (!this.active) return;
    this.node = node;
    this.ply = node ? node.ply : FIRST;
    const fen = node ? node.fen : this.data.start_fen;
    this.evalBar.show(fen, this.data.chess960 === true, this.flipped ? "b" : "w", node?.eval);
    this.board.setPosition(fen, {
      lastMove: node ? [node.uci.slice(0, 2), node.uci.slice(2, 4)] : [],
    });
    renderReviewList(byId("movelist"), this.data.moves, node, true);
    if (this.hasClocks) this.renderClocks(node);
    const last = this.data.moves[this.lastPly - 1] ?? null;
    byId("review-count").textContent = t("review.count", { ply: this.ply, total: this.lastPly });
    byId("review-first").disabled = node === null;
    byId("review-prev").disabled = node === null;
    byId("review-next").disabled = node ? node.next === null : last === null;
    byId("review-last").disabled = node === last;
    // A game can only be continued from its own moves, not from a variation.
    byId("review-play").disabled = node !== null && !node.main;
  }

  /**
   * Each side's clock after its last move up to here. In a variation, the clocks are those of the
   * main-line move it branches from; before a side's first move, its first clock.
   * @param {import("./reviewlist.js").ReviewMove | null} node
   */
  renderClocks(node) {
    let at = node;
    while (at && !at.main) at = at.prev;
    /** @type {Record<"w" | "b", number | undefined>} */
    const clocks = { w: undefined, b: undefined };
    for (const move of this.data.moves.slice(0, at ? at.ply : 0)) {
      if (move.clock_ms !== undefined) clocks[move.ply % 2 === 1 ? "w" : "b"] = move.clock_ms;
    }
    for (const side of /** @type {const} */ (["w", "b"])) {
      if (clocks[side] !== undefined) continue;
      const first = this.data.moves.find(
        (/** @type {any} */ move) => move.clock_ms !== undefined && (move.ply % 2 === 1) === (side === "w"),
      );
      clocks[side] = first?.clock_ms;
    }
    const top = this.flipped ? "w" : "b";
    const bottom = this.flipped ? "b" : "w";
    byId("top-clock").textContent = clocks[top] === undefined ? "" : formatClock(clocks[top]);
    byId("bottom-clock").textContent =
      clocks[bottom] === undefined ? "" : formatClock(clocks[bottom]);
  }

  /** @param {KeyboardEvent} event */
  onKey(event) {
    if (!this.active) return;
    const target = /** @type {HTMLElement} */ (event.target);
    if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    if (event.key === "ArrowLeft") this.back();
    else if (event.key === "ArrowRight") this.forward();
    else if (event.key === "Home") this.goTo(FIRST);
    else if (event.key === "End") this.goTo(this.lastPly);
    else if (event.key === "Escape") this.close();
    else return;
    event.preventDefault();
  }

  close() {
    if (!this.active) return;
    this.active = false;
    this.evalBar.hide();
    this.data = null;
    byId("review-bar").hidden = true;
    this.onClose();
  }
}
