// Read-only review of a saved game or a book line: arrows, keys, and clicking on a move.

import { api } from "./api.js";
import { t } from "./i18n.js";
import { EvalBar } from "./evalbar.js";
import { renderMoveList } from "./movelist.js";

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
    this.flipped = false;
    this.evalBar = new EvalBar();

    byId("review-first").addEventListener("click", () => this.goTo(FIRST));
    byId("review-prev").addEventListener("click", () => this.goTo(this.ply - 1));
    byId("review-next").addEventListener("click", () => this.goTo(this.ply + 1));
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
      const ply = Number(event.target.dataset?.ply);
      if (ply) this.goTo(ply);
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
    this.flipped = false;
    byId("review-bar").hidden = false;
    byId("review-play").hidden = gameId === null || data.chess960 === true;
    byId("top-clock").hidden = true;
    byId("bottom-clock").hidden = true;
    byId("scoresheet-note").hidden = true;
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
    this.goTo(this.ply);
  }

  /** @param {number} ply */
  goTo(ply) {
    if (!this.active) return;
    this.ply = Math.min(this.lastPly, Math.max(FIRST, ply));
    const move = this.data.moves[this.ply - 1];
    const fen = move ? move.fen : this.data.start_fen;
    this.evalBar.show(fen, this.data.chess960 === true, this.flipped ? "b" : "w");
    this.board.setPosition(fen, {
      lastMove: move ? [move.uci.slice(0, 2), move.uci.slice(2, 4)] : [],
    });
    renderMoveList(
      byId("movelist"),
      this.data.moves.map((/** @type {any} */ item) => ({
        san: item.san,
        outOfTheory: item.book !== true,
        deviation: item.deviation === true,
      })),
      true,
      this.ply,
    );
    byId("review-count").textContent = t("review.count", { ply: this.ply, total: this.lastPly });
    byId("review-first").disabled = this.ply === FIRST;
    byId("review-prev").disabled = this.ply === FIRST;
    byId("review-next").disabled = this.ply === this.lastPly;
    byId("review-last").disabled = this.ply === this.lastPly;
  }

  /** @param {KeyboardEvent} event */
  onKey(event) {
    if (!this.active) return;
    const target = /** @type {HTMLElement} */ (event.target);
    if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    if (event.key === "ArrowLeft") this.goTo(this.ply - 1);
    else if (event.key === "ArrowRight") this.goTo(this.ply + 1);
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
