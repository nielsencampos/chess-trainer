// Runs a game in the browser: local validation with chess.js for instant feedback,
// the server decides the bot's moves and what counts as theory.

import { Chess } from "./vendor/chess.js";
import { api } from "./api.js";
import { Clocks, formatClock, LOW_TIME_MS } from "./clock.js";
import { renderEndCard } from "./endcard.js";
import { t } from "./i18n.js";
import { renderMoveList } from "./movelist.js";
import { TIME_CONTROLS } from "./setup.js";

const RESIGN_CONFIRM_MS = 3000;
const AUTO_NEXT_SECONDS = 5;

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

export class GameController {
  /** @param {import("./board.js").Board} board */
  constructor(board) {
    this.board = board;
    this.chess = new Chess();
    this.clocks = new Clocks(
      (color) => this.onFlag(color),
      () => this.renderClocks(),
    );
    /** @type {import("./setup.js").GameSetup | null} */
    this.setup = null;
    /** @type {string | null} */
    this.gameId = null;
    /** @type {"w" | "b"} */
    this.userColor = "w";
    /** @type {import("./movelist.js").PlyView[]} */
    this.plies = [];
    this.inTheory = true;
    this.leftTheoryAtMove = null;
    this.over = false;
    this.botThinking = false;
    this.turnStartedAt = 0;
    // Bumped on every new game, so answers that belong to an older game are ignored.
    this.generation = 0;
    this.botTimer = 0;
    this.resignTimer = 0;
    this.autoNextTimer = 0;

    byId("resign").addEventListener("click", () => this.onResignClick());
    byId("next-game").addEventListener("click", () => this.startNext());
    byId("change-setup").addEventListener("click", () => this.leaveGame());
    byId("auto-next-cancel").addEventListener("click", () => this.cancelAutoNext());
    this.resetResign();
    this.renderIdle();
  }

  /** @param {string} square */
  legalMoves(square) {
    return this.chess.moves({ square: /** @type {any} */ (square), verbose: true }).reduce(
      (moves, move) => {
        if (!moves.some((known) => known.to === move.to)) {
          moves.push({
            to: move.to,
            capture: Boolean(move.captured),
            promotion: Boolean(move.promotion),
          });
        }
        return moves;
      },
      /** @type {import("./board.js").LegalMove[]} */ ([]),
    );
  }

  /**
   * The board before a game starts, seen from the selected color.
   * @param {"white" | "black"} [color]
   */
  renderIdle(color = "white") {
    this.chess = new Chess();
    this.board.setOrientation(color === "white" ? "w" : "b");
    this.board.setPosition(this.chess.fen());
    this.board.setMovable(null);
    this.renderNames(null);
    byId("chips").replaceChildren();
  }

  /** @param {import("./setup.js").GameSetup} setup */
  async start(setup) {
    this.cancelAutoNext();
    clearTimeout(this.botTimer);
    this.clocks.stop();
    this.generation += 1;
    const generation = this.generation;

    this.setup = setup;
    this.userColor = setup.color === "white" ? "w" : "b";
    this.chess = new Chess();
    this.plies = [];
    this.inTheory = true;
    this.leftTheoryAtMove = null;
    this.over = false;
    this.gameId = null;

    byId("setup-card").hidden = true;
    byId("end-card").hidden = true;
    byId("game-card").hidden = false;
    byId("resign").hidden = false;
    byId("game-error").hidden = true;
    byId("scoresheet-note").hidden = !setup.scoresheet;
    byId("movelist").hidden = setup.scoresheet;
    this.resetResign();

    this.board.setOrientation(this.userColor);
    this.board.setPosition(this.chess.fen());
    this.board.setMovable(null);
    this.renderNames(setup);
    this.clocks.reset(TIME_CONTROLS[setup.time_control]);
    this.renderMoves();

    // The side to move starts running at once, including a bot that opens the game.
    this.clocks.start("w");
    this.botThinking = this.userColor === "b";
    this.renderChips();

    let response;
    try {
      response = await api.newGame({
        color: setup.color,
        variant_ids: setup.variant_ids,
        level: setup.level,
        pace: setup.pace,
        time_control: setup.time_control,
      });
    } catch (error) {
      if (generation === this.generation) this.onServerError(error);
      return;
    }
    if (generation !== this.generation) return;
    this.gameId = response.state.game_id;
    const startedAt = performance.now();
    if (response.bot_move) {
      this.scheduleBotMove(response.bot_move, response.state, startedAt, generation);
    } else {
      this.beginUserTurn();
    }
  }

  beginUserTurn() {
    this.botThinking = false;
    this.turnStartedAt = performance.now();
    this.board.setMovable(this.userColor);
    this.renderChips();
  }

  /**
   * @param {string} from
   * @param {string} to
   * @param {string} [promotion]
   */
  async onUserMove(from, to, promotion) {
    if (this.over || this.gameId === null) return;
    let move;
    try {
      move = this.chess.move({ from, to, promotion });
    } catch {
      return; // chess.js rejects it; the board only offers legal moves, so this is defensive.
    }
    const generation = this.generation;
    const botColor = this.userColor === "w" ? "b" : "w";
    const thinkMs = Math.round(performance.now() - this.turnStartedAt);

    this.clocks.press(this.userColor);
    const userClockMs = this.clocks.remainingMs(this.userColor);
    const botClockMs = this.clocks.remainingMs(botColor);
    this.plies.push({ san: move.san, outOfTheory: !this.inTheory, deviation: false });
    this.showPosition([from, to]);
    this.board.setMovable(null);
    this.renderMoves();

    const gameEndedLocally = this.chess.isGameOver();
    if (!gameEndedLocally) this.clocks.start(botColor);
    this.botThinking = !gameEndedLocally;
    this.renderChips();

    const sentAt = performance.now();
    let response;
    try {
      response = await api.move(this.gameId, {
        uci: `${from}${to}${promotion ?? ""}`,
        user_clock_ms: userClockMs,
        bot_clock_ms: botClockMs,
        think_ms: thinkMs,
      });
    } catch (error) {
      if (generation === this.generation && !this.over) this.onServerError(error);
      return;
    }
    if (generation !== this.generation || this.over) return;

    const last = this.plies[this.plies.length - 1];
    last.outOfTheory = !response.user_move.in_theory;
    last.deviation = response.deviation !== null;
    this.inTheory = response.user_move.in_theory;
    if (!this.inTheory) this.leftTheoryAtMove ??= response.state.left_theory_at_move;
    this.renderMoves();
    this.renderChips();

    if (response.bot_move) {
      this.scheduleBotMove(response.bot_move, response.state, sentAt, generation);
    } else if (response.state.game_over) {
      await this.finish(generation);
    }
  }

  /**
   * Shows the bot's move once its "thinking" time has passed.
   * @param {any} botMove
   * @param {any} state
   * @param {number} sinceMs
   * @param {number} generation
   */
  scheduleBotMove(botMove, state, sinceMs, generation) {
    const wait = Math.max(0, botMove.delay_ms - (performance.now() - sinceMs));
    this.botTimer = setTimeout(() => {
      if (generation !== this.generation || this.over) return;
      this.applyBotMove(botMove, state, generation);
    }, wait);
  }

  /**
   * @param {any} botMove
   * @param {any} state
   * @param {number} generation
   */
  applyBotMove(botMove, state, generation) {
    const botColor = this.userColor === "w" ? "b" : "w";
    this.chess.move(botMove.san);
    this.clocks.press(botColor);
    this.plies.push({ san: botMove.san, outOfTheory: !botMove.in_theory, deviation: false });
    this.inTheory = botMove.in_theory;
    this.leftTheoryAtMove ??= this.inTheory ? null : state.left_theory_at_move;
    this.showPosition([botMove.uci.slice(0, 2), botMove.uci.slice(2, 4)]);
    this.renderMoves();
    if (state.game_over) {
      void this.finish(generation);
      return;
    }
    this.clocks.start(this.userColor);
    this.beginUserTurn();
  }

  /** @param {string[]} lastMove */
  showPosition(lastMove) {
    this.board.setPosition(this.chess.fen(), { lastMove, check: this.checkSquare() });
  }

  /** @returns {string | null} */
  checkSquare() {
    if (!this.chess.isCheck()) return null;
    return this.chess.findPiece({ type: "k", color: this.chess.turn() })[0] ?? null;
  }

  onResignClick() {
    const button = byId("resign");
    if (!button.classList.contains("confirming")) {
      button.classList.add("confirming");
      button.textContent = t("game.resignConfirm");
      this.resignTimer = setTimeout(() => this.resetResign(), RESIGN_CONFIRM_MS);
      return;
    }
    this.resetResign();
    void this.endWith((gameId) => api.resign(gameId));
  }

  resetResign() {
    clearTimeout(this.resignTimer);
    const button = byId("resign");
    button.classList.remove("confirming");
    button.textContent = t("game.resign");
  }

  /** @param {"w" | "b"} color */
  onFlag(color) {
    const side = color === this.userColor ? "user" : "bot";
    const shownPlies = this.plies.length;
    void this.endWith((gameId) => api.timeout(gameId, side, shownPlies));
  }

  /**
   * Ends the game with a request whose answer is the final summary.
   * @param {(gameId: string) => Promise<any>} request
   */
  async endWith(request) {
    if (this.over || this.gameId === null) return;
    const generation = this.generation;
    this.markOver();
    try {
      this.showEnd(await request(this.gameId), generation);
    } catch (error) {
      if (generation === this.generation) this.onServerError(error);
    }
  }

  /** @param {number} generation */
  async finish(generation) {
    if (this.gameId === null) return;
    this.markOver();
    try {
      this.showEnd(await api.summary(this.gameId), generation);
    } catch (error) {
      if (generation === this.generation) this.onServerError(error);
    }
  }

  markOver() {
    this.over = true;
    this.botThinking = false;
    clearTimeout(this.botTimer);
    this.clocks.stop();
    this.board.setMovable(null);
    this.renderClocks();
    this.renderChips();
  }

  /**
   * @param {any} summary
   * @param {number} generation
   */
  showEnd(summary, generation) {
    if (generation !== this.generation) return;
    this.plies = summary.moves.map((/** @type {any} */ move) => ({
      san: move.san,
      outOfTheory: !move.in_theory,
      deviation: summary.deviations.some((/** @type {any} */ item) => item.ply === move.ply),
    }));
    this.inTheory = summary.state.in_theory;
    this.leftTheoryAtMove = summary.state.left_theory_at_move;

    renderEndCard(summary);
    byId("end-card").hidden = false;
    byId("resign").hidden = true;
    byId("scoresheet-note").hidden = true;
    byId("movelist").hidden = false;
    renderMoveList(byId("movelist"), this.plies, true);
    this.renderChips();
    if (this.setup?.autoplay) this.scheduleAutoNext();
  }

  scheduleAutoNext() {
    let seconds = AUTO_NEXT_SECONDS;
    const text = byId("auto-next-text");
    const render = () => {
      text.textContent = t("end.autoNext", { seconds });
    };
    render();
    byId("auto-next").hidden = false;
    this.autoNextTimer = setInterval(() => {
      seconds -= 1;
      if (seconds <= 0) {
        this.startNext();
      } else {
        render();
      }
    }, 1000);
  }

  cancelAutoNext() {
    clearInterval(this.autoNextTimer);
    byId("auto-next").hidden = true;
  }

  startNext() {
    if (this.setup) void this.start(this.setup);
  }

  leaveGame() {
    this.cancelAutoNext();
    this.generation += 1;
    byId("end-card").hidden = true;
    byId("game-card").hidden = true;
    byId("setup-card").hidden = false;
    this.renderIdle(this.setup?.color);
    this.clocks.reset(null);
  }

  /** @param {unknown} error */
  onServerError(error) {
    console.error(error);
    this.markOver();
    byId("game-error").textContent = t("game.serverError");
    byId("game-error").hidden = false;
    byId("resign").hidden = true;
    byId("end-card").hidden = false;
    byId("end-result").textContent = t("chip.gameOver");
    byId("end-termination").textContent = "";
    byId("end-variation").textContent = "—";
    byId("end-theory").textContent = "—";
    byId("end-deviations").replaceChildren();
    byId("lichess-link").hidden = true;
    byId("copy-pgn").hidden = true;
  }

  renderMoves() {
    const showMarks = this.setup?.warning ?? true;
    renderMoveList(byId("movelist"), this.plies, showMarks);
  }

  /** @param {import("./setup.js").GameSetup | null} setup */
  renderNames(setup) {
    byId("top-name").textContent = setup
      ? t("player.bot", { level: t(`level.${setup.level}`) })
      : t("player.botIdle");
    byId("bottom-name").textContent = t("player.you");
  }

  renderClocks() {
    const top = byId("top-clock");
    const bottom = byId("bottom-clock");
    top.hidden = !this.clocks.enabled;
    bottom.hidden = !this.clocks.enabled;
    if (!this.clocks.enabled) return;
    const botColor = this.userColor === "w" ? "b" : "w";
    this.renderClock(bottom, this.userColor);
    this.renderClock(top, botColor);
  }

  /**
   * @param {HTMLElement} element
   * @param {"w" | "b"} color
   */
  renderClock(element, color) {
    const remaining = this.clocks.remaining[color];
    element.textContent = formatClock(remaining);
    element.classList.toggle("active", this.clocks.active === color);
    element.classList.toggle("low", remaining < LOW_TIME_MS);
  }

  renderChips() {
    /** @type {[string, string][]} */
    const chips = [];
    const warning = this.setup?.warning ?? true;
    if (this.over) {
      chips.push([t("chip.gameOver"), ""]);
    } else if (this.botThinking) {
      chips.push([t("chip.botThinking"), ""]);
    } else {
      chips.push([t("chip.yourMove"), "chip-accent"]);
    }
    if (warning || this.over) {
      if (this.inTheory) {
        chips.push([t("chip.inTheory"), "chip-accent"]);
      } else if (this.leftTheoryAtMove !== null) {
        chips.push([t("chip.leftTheory", { move: this.leftTheoryAtMove }), "chip-warn"]);
      }
    }
    if (!this.over && this.chess.isCheck()) chips.push([t("chip.check"), "chip-bad"]);
    byId("chips").replaceChildren(
      ...chips.map(([text, className]) => {
        const chip = document.createElement("span");
        chip.className = `chip ${className}`;
        chip.textContent = text;
        return chip;
      }),
    );
  }
}
