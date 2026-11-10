// Runs a game in the browser: local validation with rules.js for instant feedback,
// the server decides the bot's moves and what counts as theory.

import { api } from "./api.js";
import { Clocks, formatClock } from "./clock.js";
import { renderEndCard } from "./endcard.js";
import { openingName } from "./opening-names.js";
import { showPage } from "./pages.js";
import { EvalBar } from "./evalbar.js";
import { t } from "./i18n.js";
import { levelLabel } from "./levels.js";
import { renderMoveList } from "./movelist.js";
import { getPref, setPref } from "./prefs.js";
import { premoveDestinations } from "./premove.js";
import { Rules } from "./rules.js";
import { sound } from "./sound.js";

const RESIGN_CONFIRM_MS = 3000;

/**
 * Finds an element by id.
 * @param {string} id  The element's id.
 * @returns {any} The element.
 */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/** Runs a game in the browser: moves, clocks, premove, take-back, the bars and the end card. */
export class GameController {
  /**
   * Creates the controller with no game, and wires Show moves, Resign and Take back.
   * @param {import("./board.js").Board} board  The board it plays on.
   */
  constructor(board) {
    this.board = board;
    this.rules = new Rules();
    /** @type {() => string | undefined} The Chess960 position the setup shows, if any. */
    this.previewFen = () => undefined;
    /** A finished game is still on screen, with the menu back on the left. */
    this.ended = false;
    this.evalBar = new EvalBar();
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
    /** @type {{ply: number, move_number: number, played_san: string, expected_san: string[]} | null} The bot's deviation. */
    this.botDeviation = null;
    /** @type {{from: string, to: string} | null} */
    this.premove = null;
    /** @type {{eco: string, name: string} | null} */
    this.opening = null;
    this.over = false;
    this.botThinking = false;
    this.turnStartedAt = 0;
    // Bumped on every new game, so answers that belong to an older game are ignored.
    this.generation = 0;
    this.botTimer = 0;
    this.resignTimer = 0;
    /**
     * Between the server's answer and the moment the bot's reply is shown, the user's move can be
     * taken back. This is what the board and clocks were before that move.
     * @type {{clocks: {w: number | null, b: number | null}} | null}
     */
    this.takeBackable = null;
    /** @type {any} The final summary while the end-of-game card shows it. */
    this.summary = null;
    /** The server failed and the end-of-game card says so. */
    this.failed = false;

    // "Show moves" is a bar preference: it can change at any moment, mid-game included.
    this.showMoves = getPref("showMoves", true) !== false;
    const showMoves = byId("show-moves");
    showMoves.checked = this.showMoves;
    showMoves.addEventListener("change", () => {
      this.showMoves = showMoves.checked;
      setPref("showMoves", this.showMoves);
      this.applyShowMoves();
    });

    byId("resign").addEventListener("click", () => this.onResignClick());
    byId("take-back").addEventListener("click", () => void this.onTakeBack());
    this.resetResign();
    this.renderIdle();
  }

  /**
   * The legal moves of a piece, for the board.
   * @param {string} square  The piece's square.
   * @returns {import("./rules.js").TargetMove[]} Its destinations.
   */
  legalMoves(square) {
    return this.rules.movesFrom(square);
  }

  /**
   * Where one of the user's pieces could be premoved, by its shape alone.
   * @param {string} square  The piece's square.
   * @returns {import("./board.js").LegalMove[]} Its destinations; none for the bot's pieces.
   */
  premoveTargets(square) {
    const piece = this.rules.pieceAt(square);
    if (!piece || piece.color !== this.userColor) return [];
    return premoveDestinations(square, piece, this.rules.chess960).map((to) => ({
      to,
      capture: false,
      promotion: false,
    }));
  }

  /**
   * Queues a premove.
   * @param {string} from  The piece's square.
   * @param {string} to  The target square.
   * @returns {void}
   */
  setPremove(from, to) {
    this.premove = { from, to };
    this.board.setPremoveSquares([from, to]);
    this.renderChips();
  }

  /** Drops the queued premove, if any. */
  clearPremove() {
    this.premove = null;
    this.board.setPremoveSquares([]);
    this.renderChips();
  }

  /**
   * The user's color while the bot is thinking, if premoves are on.
   * @returns {"w" | "b" | null} The color, or null with premoves off.
   */
  premoveColor() {
    return this.setup?.premoves ? this.userColor : null;
  }

  /** Plays the queued premove if it is legal now, and drops it otherwise. */
  playPremove() {
    const queued = this.premove;
    if (!queued) return;
    this.clearPremove();
    const legal = this.rules.movesFrom(queued.from).find((move) => move.to === queued.to);
    if (legal) void this.onUserMove(queued.from, queued.to, legal.promotion ? "q" : undefined);
  }

  /**
   * The board before a game starts, seen from the selected color.
   * @param {"white" | "black"} [color]  The color at the bottom.
   * @param {string} [chess960Fen]  The Chess960 position the setup shows, if any.
   * @returns {void}
   */
  renderIdle(color = "white", chess960Fen) {
    this.rules = new Rules(chess960Fen);
    this.board.setOrientation(color === "white" ? "w" : "b");
    this.board.setPosition(this.rules.fen());
    this.board.setMovable(null);
    this.renderNames(null);
    this.plies = [];
    this.opening = null;
    this.over = false;
    this.setup = null;
    this.summary = null;
    this.failed = false;
    this.clearPremove();
    this.applyShowMoves();
    this.renderMoves();
    this.renderOpening();
    byId("chips").replaceChildren(); // Last: clearing the premove draws them.
  }

  /**
   * Starts a new game on the server, and shows the bot's first move if it opens.
   * @param {import("./setup.js").GameSetup} setup  The game's setup.
   * @returns {Promise<void>}
   */
  async start(setup) {
    clearTimeout(this.botTimer);
    this.clocks.stop();
    this.generation += 1;
    const generation = this.generation;

    this.prepare(setup);
    sound.play("start");

    // The side to move starts running at once, including a bot that opens the game.
    this.clocks.start("w");
    this.botThinking = this.userColor === "b";
    if (this.botThinking) this.board.setMovable(null, this.premoveColor());
    this.renderChips();

    // The bot's clock is already running, so its delay counts from here.
    const sentAt = performance.now();
    let response;
    try {
      response = await api.newGame({
        color: setup.color,
        variant_ids: setup.variant_ids,
        from_game: setup.from_game ?? undefined,
        chess960_position: setup.chess960?.position,
        level: setup.level,
        pace: setup.pace,
        time_control: setup.time_control,
        ui: {
          warning: setup.warning,
          premoves: setup.premoves,
        },
        bot_deviation: setup.deviate ?? undefined,
      });
    } catch (error) {
      if (generation === this.generation) this.onServerError(error);
      return;
    }
    if (generation !== this.generation) return;
    if (setup.from_game?.mode === "position") {
      // The board starts with the game's moves, which is the same as continuing a saved game.
      const { game } = await api.activeGame();
      if (generation === this.generation) this.resume(game, setup.clock);
      return;
    }
    this.gameId = response.state.game_id;
    if (response.bot_move) {
      this.scheduleBotMove(response.bot_move, response.state, sentAt, generation);
    } else {
      this.beginUserTurn();
    }
  }

  /**
   * Resets the board, clocks, bars and lists for a game, before any move.
   * @param {import("./setup.js").GameSetup} setup  The game's setup.
   * @returns {void}
   */
  prepare(setup) {
    this.setup = setup;
    this.summary = null;
    this.failed = false;
    this.userColor = setup.color === "white" ? "w" : "b";
    this.rules = new Rules(setup.chess960?.fen);
    this.plies = [];
    this.inTheory = !setup.chess960;
    this.leftTheoryAtMove = null;
    this.botDeviation = null;
    this.over = false;
    this.gameId = null;
    this.clearPremove();

    byId("setup-card").hidden = true;
    byId("saved-card").hidden = true;
    byId("import-card").hidden = true;
    showPage(null);
    this.ended = false;
    this.evalBar.hide();
    this.takeBackable = null;
    byId("sidebar-tabs").hidden = true;
    byId("end-card").hidden = true;
    byId("copy-pgn").hidden = false;
    byId("download-pgn").hidden = false;
    byId("game-card").hidden = false;
    byId("resign").hidden = false;
    byId("game-error").hidden = true;
    this.applyShowMoves();
    this.resetResign();
    this.renderTakeBack();

    this.board.setOrientation(this.userColor);
    this.board.setPosition(this.rules.fen());
    this.board.setMovable(null);
    this.renderNames(setup);
    this.clocks.reset(setup.clock);
    this.renderMoves();
    this.opening = null;
    this.renderOpening();
  }

  /**
   * Continues a saved game, as it was at its last saved move.
   * @param {any} game  The API's ActiveGame.
   * @param {import("./setup.js").TimeControlInfo | null} clock  Its time control, or null.
   * @returns {void}
   */
  resume(game, clock) {
    this.generation += 1;
    const generation = this.generation;
    const { ui } = game.setup;
    this.prepare({
      color: game.setup.color,
      variant_ids: game.setup.variant_ids,
      chess960: game.setup.chess960,
      level: game.setup.level,
      pace: game.setup.pace,
      time_control: game.setup.time_control,
      clock,
      warning: ui.warning ?? true,
      premoves: ui.premoves ?? true,
    });
    for (const move of game.moves) this.rules.moveSan(move.san);
    this.plies = game.moves.map((/** @type {any} */ move) => ({
      san: move.san,
      uci: move.uci,
      outOfTheory: !move.in_theory,
      deviation: move.deviation,
    }));
    this.gameId = game.state.game_id;
    this.inTheory = game.state.in_theory;
    this.leftTheoryAtMove = game.state.left_theory_at_move;
    this.botDeviation = game.state.bot_deviation ?? null;
    this.opening = game.state.opening;

    const botColor = this.userColor === "w" ? "b" : "w";
    /**
     * Counts the saved moves of one side.
     * @param {string} by  `user` or `bot`.
     * @returns {number} The count.
     */
    const countBy = (/** @type {string} */ by) =>
      game.moves.filter((/** @type {any} */ move) => move.by === by).length;
    this.clocks.restore(
      { [this.userColor]: game.clocks.user_ms, [botColor]: game.clocks.bot_ms },
      { [this.userColor]: countBy("user"), [botColor]: countBy("bot") },
    );
    const last = game.moves[game.moves.length - 1];
    if (last) this.showPosition([last.uci.slice(0, 2), last.uci.slice(2, 4)]);
    this.renderMoves();
    this.renderOpening();
    if (game.state.game_over) {
      void this.finish(generation);
      return;
    }
    this.clocks.start(this.userColor);
    this.beginUserTurn();
  }

  /** Lets the user move and starts timing the move. */
  beginUserTurn() {
    this.botThinking = false;
    this.turnStartedAt = performance.now();
    this.board.setMovable(this.userColor);
    this.renderChips();
  }

  /**
   * Plays the user's move at once, sends it, and schedules the bot's reply.
   * @param {string} from  The piece's square.
   * @param {string} to  The target square.
   * @param {string} [promotion]  The piece to promote to.
   * @returns {Promise<void>}
   */
  async onUserMove(from, to, promotion) {
    if (this.over || this.gameId === null) return;
    const before = { w: this.clocks.remainingMs("w"), b: this.clocks.remainingMs("b") };
    const move = this.rules.move(from, to, promotion);
    if (!move) return; // The board only offers legal moves, so this is defensive.
    const generation = this.generation;
    const botColor = this.userColor === "w" ? "b" : "w";
    const thinkMs = Math.round(performance.now() - this.turnStartedAt);

    this.clocks.press(this.userColor);
    const userClockMs = this.clocks.remainingMs(this.userColor);
    const botClockMs = this.clocks.remainingMs(botColor);
    sound.playMove(move, false);
    this.plies.push({ san: move.san, uci: move.uci, outOfTheory: !this.inTheory, deviation: false });
    this.showPosition([from, to]);
    const gameEndedLocally = this.rules.isGameOver();
    this.board.setMovable(null, gameEndedLocally ? null : this.premoveColor());
    this.renderMoves();

    if (!gameEndedLocally) this.clocks.start(botColor);
    this.botThinking = !gameEndedLocally;
    this.renderChips();

    const sentAt = performance.now();
    let response;
    try {
      response = await api.move(this.gameId, {
        uci: move.uci,
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
    this.opening = response.user_move.opening ?? this.opening;
    this.renderOpening();
    this.renderMoves();
    this.renderChips();

    if (response.bot_move) {
      this.takeBackable = { clocks: before };
      this.renderTakeBack();
      this.scheduleBotMove(response.bot_move, response.state, sentAt, generation);
    } else if (response.state.game_over) {
      await this.finish(generation);
    }
  }

  /**
   * Shows the bot's move once its "thinking" time has passed.
   * @param {any} botMove  The API's BotMoveOut.
   * @param {any} state  The game's state after it.
   * @param {number} sinceMs  When its clock started, from `performance.now()`.
   * @param {number} generation  The game the answer belongs to; an older one is ignored.
   * @returns {void}
   */
  scheduleBotMove(botMove, state, sinceMs, generation) {
    const wait = Math.max(0, botMove.delay_ms - (performance.now() - sinceMs));
    this.botTimer = setTimeout(() => {
      if (generation !== this.generation || this.over) return;
      this.applyBotMove(botMove, state, generation);
    }, wait);
  }

  /**
   * Plays the bot's move on the board, then ends the game or gives the user the turn.
   * @param {any} botMove  The API's BotMoveOut.
   * @param {any} state  The game's state after it.
   * @param {number} generation  The game the answer belongs to; an older one is ignored.
   * @returns {void}
   */
  applyBotMove(botMove, state, generation) {
    const botColor = this.userColor === "w" ? "b" : "w";
    this.takeBackable = null;
    this.renderTakeBack();
    sound.playMove(this.rules.moveSan(botMove.san), true);
    this.clocks.press(botColor);
    this.plies.push({
      san: botMove.san,
      uci: botMove.uci,
      outOfTheory: !botMove.in_theory,
      deviation: false,
    });
    this.inTheory = botMove.in_theory;
    this.leftTheoryAtMove ??= this.inTheory ? null : state.left_theory_at_move;
    this.botDeviation = state.bot_deviation ?? null;
    this.showPosition([botMove.uci.slice(0, 2), botMove.uci.slice(2, 4)]);
    this.opening = botMove.opening ?? this.opening;
    this.renderOpening();
    this.renderMoves();
    if (state.game_over) {
      void this.finish(generation);
      return;
    }
    this.clocks.start(this.userColor);
    this.beginUserTurn();
    this.playPremove();
  }

  /**
   * Shows the current position, with its last move and check.
   * @param {string[]} lastMove  The last move's squares, or none.
   * @returns {void}
   */
  showPosition(lastMove) {
    this.board.setPosition(this.rules.fen(), { lastMove, check: this.checkSquare() });
  }

  /**
   * The square of the king in check.
   * @returns {string | null} The square, or null.
   */
  checkSquare() {
    return this.rules.checkSquare();
  }

  /**
   * Shows Take back only without premoves (with them, a move queued for the reply is the way
   * to play fast), enabled while the bot's reply is not shown yet.
   */
  renderTakeBack() {
    const button = byId("take-back");
    button.hidden = this.setup?.premoves ?? true;
    button.disabled = this.takeBackable === null;
  }

  /**
   * Takes back the user's last move and the bot's unseen reply, with the clocks before it.
   * @returns {Promise<void>}
   */
  async onTakeBack() {
    const saved = this.takeBackable;
    if (!saved || this.over || this.gameId === null) return;
    this.takeBackable = null;
    this.renderTakeBack();
    clearTimeout(this.botTimer);
    this.clearPremove();
    this.generation += 1; // The scheduled reply, if it fires anyway, is ignored.
    const generation = this.generation;
    let state;
    try {
      state = await api.takeBack(this.gameId, {
        shown_plies: this.plies.length,
        user_clock_ms: saved.clocks[this.userColor],
        bot_clock_ms: saved.clocks[this.userColor === "w" ? "b" : "w"],
      });
    } catch (error) {
      if (generation === this.generation && !this.over) this.onServerError(error);
      return;
    }
    if (generation !== this.generation || this.over) return;

    this.plies.pop();
    this.rules = new Rules(this.setup?.chess960?.fen);
    for (const ply of this.plies) this.rules.moveSan(ply.san);
    this.inTheory = state.in_theory;
    this.leftTheoryAtMove = state.left_theory_at_move;
    this.botDeviation = state.bot_deviation ?? null;
    this.opening = state.opening ?? null;
    // White moves first, so a ply's index says whose it was.
    const white = this.plies.filter((_, index) => index % 2 === 0).length;
    this.clocks.restore(saved.clocks, { w: white, b: this.plies.length - white });
    const last = this.plies[this.plies.length - 1];
    this.showPosition(last?.uci ? [last.uci.slice(0, 2), last.uci.slice(2, 4)] : []);
    this.renderOpening();
    this.renderMoves();
    this.clocks.start(this.userColor);
    this.beginUserTurn();
  }

  /** Resign needs a second click within 3 s to confirm. */
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

  /** Puts the Resign button back to its first state. */
  resetResign() {
    clearTimeout(this.resignTimer);
    const button = byId("resign");
    button.classList.remove("confirming");
    button.textContent = t("game.resign");
  }

  /**
   * A clock in the browser ran out: the server ends the game.
   * @param {"w" | "b"} color  Whose clock ran out.
   * @returns {void}
   */
  onFlag(color) {
    const side = color === this.userColor ? "user" : "bot";
    const shownPlies = this.plies.length;
    void this.endWith((gameId) => api.timeout(gameId, side, shownPlies));
  }

  /**
   * Ends the game with a request whose answer is the final summary.
   * @param {(gameId: string) => Promise<any>} request  The request, such as resign.
   * @returns {Promise<void>}
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

  /**
   * Shows the end of a game that ended on the board.
   * @param {number} generation  The game the answer belongs to; an older one is ignored.
   * @returns {Promise<void>}
   */
  async finish(generation) {
    if (this.gameId === null) return;
    this.markOver();
    try {
      this.showEnd(await api.summary(this.gameId), generation);
    } catch (error) {
      if (generation === this.generation) this.onServerError(error);
    }
  }

  /** Stops everything that runs during a game: clocks, bot, premove and input. */
  markOver() {
    this.takeBackable = null;
    this.renderTakeBack();
    this.over = true;
    this.botThinking = false;
    clearTimeout(this.botTimer);
    this.clocks.stop();
    this.board.setMovable(null);
    this.premove = null;
    this.board.setPremoveSquares([]);
    this.renderClocks();
    this.renderChips();
    this.applyShowMoves();
  }

  /**
   * The plies for the move list, with the bot's deviation marked.
   * @returns {import("./movelist.js").PlyView[]} The plies.
   */
  markedPlies() {
    const ply = this.botDeviation?.ply;
    return this.plies.map((view, index) => (index + 1 === ply ? { ...view, botDeviation: true } : view));
  }

  /**
   * Shows the end-of-game card, the final move list and the evaluation bar.
   * @param {any} summary  The API's GameSummary.
   * @param {number} generation  The game the answer belongs to; an older one is ignored.
   * @returns {void}
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
    this.botDeviation = summary.state.bot_deviation ?? null;
    this.opening = summary.state.opening ?? this.opening;
    this.renderOpening();

    sound.play("end");
    this.summary = summary;
    renderEndCard(summary);
    byId("end-card").hidden = false;
    byId("resign").hidden = true;
    renderMoveList(byId("movelist"), this.markedPlies(), true);
    this.renderChips();
    this.showMenu();
    this.evalBar.show(this.rules.fen(), this.rules.chess960, this.userColor);
  }

  /**
   * After a game, the left column is the menu again and the board keeps the final position.
   * No item is active: clicking any of them leaves the game.
   */
  showMenu() {
    this.ended = true;
    byId("sidebar-tabs").hidden = false;
    byId("game-card").hidden = byId("game-error").hidden;
    for (const tab of document.querySelectorAll("#sidebar-tabs .tab")) tab.classList.remove("active");
  }

  /** Leaves a finished game for another screen of the menu. */
  leaveGame() {
    if (!this.ended) return;
    this.ended = false;
    this.generation += 1;
    this.evalBar.hide();
    byId("end-card").hidden = true;
    byId("game-card").hidden = true;
    const color = this.setup?.color;
    this.renderIdle(color, this.previewFen());
    this.clocks.reset(null);
  }

  /**
   * Ends the game on screen when the server fails, and says so on the end card.
   * @param {unknown} error  The error, logged to the console.
   * @returns {void}
   */
  onServerError(error) {
    console.error(error);
    this.markOver();
    this.failed = true;
    this.renderFailure();
    byId("game-error").hidden = false;
    byId("resign").hidden = true;
    byId("end-card").hidden = false;
    byId("end-termination").textContent = "";
    byId("end-variation").textContent = "—";
    byId("end-theory").textContent = "—";
    byId("end-deviations").replaceChildren();
    byId("copy-pgn").hidden = true;
    byId("download-pgn").hidden = true;
    this.showMenu();
  }

  /** Writes the server-error texts in the current language. */
  renderFailure() {
    byId("game-error").textContent = t("game.serverError");
    byId("end-result").textContent = t("chip.gameOver");
  }

  /** Draws again, in the language just chosen, what the game shows around the board. */
  relocalize() {
    this.renderNames(this.setup);
    this.renderOpening();
    if (this.summary) {
      renderMoveList(byId("movelist"), this.markedPlies(), true);
      renderEndCard(this.summary);
    } else {
      this.renderMoves();
    }
    if (this.failed) this.renderFailure();
    if (this.setup !== null) this.renderChips();
    const resign = byId("resign");
    resign.textContent = t(resign.classList.contains("confirming") ? "game.resignConfirm" : "game.resign");
  }

  /**
   * With "Show moves" off, the opening name and the move list, with their headings, are hidden
   * while a game is played. Everything shows again at the end of the game, and outside games.
   */
  applyShowMoves() {
    const playing = this.setup !== null && !this.over;
    byId("show-moves-option").hidden = !playing; // The checkbox matters only during a game.
    const hidden = !this.showMoves && playing;
    // The headings go too: an empty "Opening" and "Moves" would only take room.
    byId("opening-box").hidden = hidden;
    byId("moves-box").hidden = hidden;
  }

  /** Writes the opening name, or that there is none yet. */
  renderOpening() {
    byId("opening-name").textContent =
      this.opening
        ? t("moves.openingName", { eco: this.opening.eco, name: openingName(this.opening.name) })
        : t("moves.noOpening");
  }

  /** Draws the move list, with theory marks unless the warning is off or there is no book. */
  renderMoves() {
    // Without a book, no move is in or out of theory.
    const showMarks = (this.setup?.warning ?? true) && !this.setup?.chess960;
    renderMoveList(byId("movelist"), this.markedPlies(), showMarks);
  }

  /**
   * Writes the players' names above and below the board.
   * @param {import("./setup.js").GameSetup | null} setup  The game's setup, or null before a game.
   * @returns {void}
   */
  renderNames(setup) {
    byId("top-name").textContent = setup
      ? t("player.bot", { level: levelLabel(setup.level) })
      : t("player.botIdle");
    byId("bottom-name").textContent = t("player.you");
  }

  /** Draws both clocks, or hides them without a clock. */
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
   * Draws one clock: the time, and whether it runs or is low.
   * @param {HTMLElement} element  The clock's element.
   * @param {"w" | "b"} color  Whose clock.
   * @returns {void}
   */
  renderClock(element, color) {
    const remaining = this.clocks.remaining[color];
    element.textContent = formatClock(remaining);
    element.classList.toggle("active", this.clocks.active === color);
    element.classList.toggle("low", remaining < this.clocks.lowTime);
  }

  /** Draws the status chips under the board: turn, theory, check and premove. */
  renderChips() {
    /** @type {[string, string][]} */
    const chips = [];
    const warning = this.setup?.warning ?? true;
    if (this.over) {
      chips.push([t("chip.gameOver"), ""]);
    } else if (this.botThinking) {
      chips.push([t("chip.botThinking"), ""]);
    } else if (this.gameId !== null) {
      // Without a game id the server has not answered yet and the board is still locked.
      chips.push([t("chip.yourMove"), "chip-accent"]);
    }
    if (warning || this.over) {
      if (this.inTheory) {
        chips.push([t("chip.inTheory"), "chip-accent"]);
      } else if (this.botDeviation) {
        chips.push([t("chip.botDeviated", { move: this.botDeviation.move_number }), "chip-warn"]);
      } else if (this.leftTheoryAtMove !== null) {
        chips.push([t("chip.leftTheory", { move: this.leftTheoryAtMove }), "chip-warn"]);
      }
    }
    if (!this.over && this.rules.isCheck()) chips.push([t("chip.check"), "chip-bad"]);
    if (this.premove) chips.push([t("chip.premove"), "chip-warn"]);
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
