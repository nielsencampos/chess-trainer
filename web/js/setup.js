// The setup card: color, openings and variations, level, clock, pace, options.

import { api } from "./api.js";
import { t } from "./i18n.js";
import { OpeningTree } from "./opening-tree.js";
import { getPref, setPref } from "./prefs.js";


/**
 * @typedef {{variant_id: string, names: Record<string, string>, eco: string | null,
 *   opening: string | null, pgn: string, subgroup: Record<string, string> | null}} VariantInfo
 * @typedef {{repertoire_id: string, names: Record<string, string>, group: string,
 *   order: number | null, variants: VariantInfo[]}} RepertoireInfo
 * @typedef {{key: string, base_ms: number, increment_ms: number,
 *   periods: {after_moves: number, add_ms: number}[],
 *   delay_ms: number, delay_kind: string | null}} TimeControlInfo
 * @typedef {{key: string, items: TimeControlInfo[]}} TimeControlGroup
 * @typedef {{groups: TimeControlGroup[], no_clock: string, default: string}} TimeControls
 * @typedef {{
 *   color: "white" | "black", variant_ids: string[], level: string, pace: "human" | "instant",
 *   time_control: string, clock: TimeControlInfo | null,
 *   from_game?: {game_id: string, upto_ply: number, mode: string} | null,
 *   chess960?: {position: number, fen: string} | null,
 *   warning: boolean, premoves: boolean,
 * }} GameSetup
 */

/** @param {string} selector */
const radios = (selector) => /** @type {NodeListOf<HTMLInputElement>} */ (document.querySelectorAll(selector));

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

export class SetupCard {
  /**
   * @param {RepertoireInfo[]} repertoires
   * @param {string[]} levels
   * @param {string} defaultLevel
   * @param {TimeControls} timeControls
   * @param {(color: "white" | "black") => void} onColorChange
   * @param {(setup: GameSetup) => void} onPlay
   */
  constructor(repertoires, levels, defaultLevel, timeControls, onColorChange, onPlay) {
    this.repertoires = repertoires; // Already in the book's order.
    this.onColorChange = onColorChange;
    const known = new Set(repertoires.flatMap((rep) => rep.variants.map((v) => v.variant_id)));
    this.tree = new OpeningTree(
      repertoires,
      {
        search: byId("opening-search"),
        container: byId("openings"),
        total: byId("selected-total"),
        selectAll: byId("select-all"),
        clear: byId("clear-selection"),
        noMatches: byId("no-matches"),
      },
      getPref("selected", []).filter((/** @type {string} */ id) => known.has(id)),
      (selected) => {
        setPref("selected", [...selected]);
        this.updateSelectionState();
      },
    );

    const levelSelect = byId("level");
    for (const key of levels) levelSelect.add(new Option(t(`level.${key}`), key));
    levelSelect.value = getPref("level", defaultLevel);

    this.timeControls = timeControls;
    const timeSelect = byId("time-control");
    for (const group of timeControls.groups) {
      const optgroup = document.createElement("optgroup");
      optgroup.label = t(`setup.group.${group.key}`);
      for (const item of group.items) optgroup.append(new Option(this.timeLabel(item), item.key));
      timeSelect.append(optgroup);
    }
    timeSelect.add(new Option(t("setup.noClock"), timeControls.no_clock));
    timeSelect.value = getPref("timeControl", timeControls.default);
    if (timeSelect.value === "") timeSelect.value = timeControls.default; // A removed one was saved.

    this.setRadio("color", getPref("color", "white"));
    this.setRadio("pace", getPref("pace", "human"));
    byId("opt-warning").checked = getPref("warning", true);
    byId("opt-premoves").checked = getPref("premoves", true);

    for (const radio of radios('input[name="color"]')) {
      radio.addEventListener("change", () => {
        setPref("color", this.color);
        this.onColorChange(this.color);
      });
    }
    /** @type {"opening" | "saved"} */
    this.mode = "opening";
    this.shown = true;
    // Disabled until here, so a choice made while the page loads is not lost.
    for (const radio of radios('input[name="new-mode"]')) {
      radio.addEventListener("change", () => void this.setMode(/** @type {any} */ (radio.value)));
      radio.disabled = false;
    }
    /** @type {any[]} */
    this.savedGames = [];
    /** @type {string | null} */
    this.savedGameId = null;
    byId("from-saved-search").addEventListener("input", () => this.renderSavedGames());
    for (const radio of radios('input[name="from-mode"]')) {
      radio.addEventListener("change", () => this.renderFromSavedHelp());
    }
    this.renderFromSavedHelp();
    /** @type {{position: number, fen: string} | null} */
    this.chess960 = null;
    byId("chess960-roll").addEventListener("click", () => void this.loadChess960());
    byId("chess960-fen-form").addEventListener("submit", (/** @type {Event} */ event) => {
      event.preventDefault();
      const fen = byId("chess960-fen").value.trim();
      if (fen) void this.loadChess960(fen);
    });
    byId("play").addEventListener("click", () => {
      const setup = this.read();
      this.save(setup);
      onPlay(setup);
    });
    this.updateSelectionState();
  }

  /** @param {TimeControlInfo} item */
  timeLabel(item) {
    const minutes = [item.base_ms, ...item.periods.map((period) => period.add_ms)]
      .map((ms) => ms / 60_000)
      .join(" + ");
    const seconds = (item.increment_ms + item.delay_ms) / 1000;
    let extra = "";
    if (item.increment_ms > 0) extra = t("setup.tc.increment", { seconds });
    if (item.delay_kind === "bronstein") extra = t("setup.tc.delay", { seconds });
    if (item.delay_kind === "us") extra = t("setup.tc.usDelay", { seconds });
    if (item.base_ms < 60_000) return t("setup.tc.seconds", { seconds: item.base_ms / 1000 });
    return `${t("setup.tc.minutes", { minutes })}${extra}`;
  }

  /** @param {string} key */
  timeLabelFor(key) {
    const item = this.clockFor(key);
    return item ? this.timeLabel(item) : key;
  }

  /** @returns {TimeControlInfo | null} */
  selectedClock() {
    return this.clockFor(byId("time-control").value);
  }

  /**
   * @param {string} key
   * @returns {TimeControlInfo | null}
   */
  clockFor(key) {
    return (
      this.timeControls.groups.flatMap((group) => group.items).find((item) => item.key === key) ??
      null
    );
  }

  /**
   * @param {string} name
   * @param {string} value
   */
  setRadio(name, value) {
    for (const radio of radios(`input[name="${name}"]`)) radio.checked = radio.value === value;
  }

  /** @param {string} name */
  radioValue(name) {
    return /** @type {HTMLInputElement | null} */ (
      document.querySelector(`input[name="${name}"]:checked`)
    )?.value;
  }

  /** @returns {"white" | "black"} */
  get color() {
    return /** @type {"white" | "black"} */ (this.radioValue("color"));
  }

  /** The position the board shows while choosing, if it is not the normal one. */
  previewFen() {
    return this.shown && this.mode === "chess960" ? this.chess960?.fen : undefined;
  }

  /**
   * Rolls the dice, or uses the position the user typed.
   * @param {string} [fen]
   */
  async loadChess960(fen) {
    byId("chess960-error").hidden = true;
    try {
      this.chess960 = await api.chess960Start(fen);
    } catch (error) {
      console.error(error);
      byId("chess960-error").hidden = false;
      return;
    }
    if (!fen) byId("chess960-fen").value = "";
    byId("chess960-number").textContent = t("chess960.position", {
      number: /** @type {{position: number}} */ (this.chess960).position,
    });
    this.updateSelectionState();
    this.onColorChange(this.color);
  }

  /**
   * The setup is on screen, so the board can show what it is choosing.
   * @param {boolean} shown
   */
  setShown(shown) {
    if (shown === this.shown) return;
    this.shown = shown;
    this.onColorChange(this.color);
  }

  /** @param {"opening" | "saved" | "chess960"} mode */
  async setMode(mode) {
    const changed = mode !== this.mode;
    this.mode = mode;
    this.setRadio("new-mode", mode);
    byId("openings-field").hidden = mode !== "opening";
    byId("from-saved").hidden = mode !== "saved";
    byId("chess960").hidden = mode !== "chess960";
    this.updateSelectionState();
    if (changed) this.onColorChange(this.color);
    if (mode === "chess960" && !this.chess960) await this.loadChess960();
    if (mode !== "saved") return;
    try {
      this.savedGames = (await api.savedGames()).games;
    } catch (error) {
      console.error(error);
      this.savedGames = [];
    }
    if (!this.savedGames.some((game) => game.game_id === this.savedGameId)) this.savedGameId = null;
    this.renderSavedGames();
  }

  /**
   * @param {string} gameId
   * @param {number} ply
   */
  async chooseSaved(gameId, ply) {
    await this.setMode("saved");
    this.savedGameId = gameId;
    this.renderSavedGames();
    if (ply > 0) byId("from-saved-ply").value = String(ply);
    this.setRadio("from-mode", "position");
    this.renderFromSavedHelp();
  }

  renderFromSavedHelp() {
    const mode = this.radioValue("from-mode");
    byId("from-saved-help").textContent = t(
      mode === "position" ? "fromSaved.positionHelp" : "fromSaved.lineHelp",
    );
  }

  renderSavedGames() {
    const query = byId("from-saved-search").value.trim().toLowerCase();
    const games = this.savedGames.filter(
      (game) =>
        !query ||
        `${game.eco ?? ""} ${game.opening ?? ""} ${game.white ?? ""} ${game.black ?? ""}`
          .toLowerCase()
          .includes(query),
    );
    byId("from-saved-list").replaceChildren(...games.map((game) => this.savedGameRow(game)));
    byId("from-saved-empty").hidden = this.savedGames.length > 0;
    this.renderPlyOptions();
    this.updateSelectionState();
  }

  /** @param {any} game */
  savedGameRow(game) {
    const label = document.createElement("label");
    label.className = `saved-game${game.chess960 ? " is-disabled" : ""}`;
    const box = document.createElement("input");
    box.type = "radio";
    box.name = "from-saved-game";
    box.value = game.game_id;
    box.disabled = game.chess960;
    box.checked = this.savedGameId === game.game_id;
    box.addEventListener("change", () => {
      this.savedGameId = game.game_id;
      this.renderPlyOptions();
      this.updateSelectionState();
    });
    const text = document.createElement("span");
    text.className = "variant-text";
    const name = document.createElement("span");
    const eco = game.eco ? `${game.eco} · ` : "";
    name.textContent = `${eco}${game.opening ?? t("saved.noOpening")}`;
    const details = document.createElement("span");
    details.className = "variant-moves";
    const who = game.source === "imported" ? `${game.white} - ${game.black}` : t(`setup.${game.user_color}`);
    details.textContent = [
      new Date(game.started_at).toLocaleDateString(),
      who,
      t("saved.plies", { count: game.plies }),
      ...(game.chess960 ? [t("fromSaved.chess960")] : []),
    ].join(" · ");
    text.append(name, details);
    label.append(box, text);
    return label;
  }

  renderPlyOptions() {
    const select = byId("from-saved-ply");
    select.replaceChildren();
    const game = this.savedGames.find((item) => item.game_id === this.savedGameId);
    select.disabled = !game;
    if (!game) return;
    select.add(new Option(t("fromSaved.end", { plies: game.plies }), String(game.plies)));
    game.sans.forEach((/** @type {string} */ san, /** @type {number} */ index) => {
      const number = Math.floor(index / 2) + 1;
      const dots = index % 2 === 0 ? "." : "...";
      select.add(new Option(`${number}${dots} ${san}`, String(index + 1)));
    });
  }

  updateSelectionState() {
    let ready = this.tree.selected.size > 0;
    let hint = "setup.selectOne";
    if (this.mode === "saved") {
      ready = this.savedGameId !== null;
      hint = "setup.selectGame";
    } else if (this.mode === "chess960") {
      ready = this.chess960 !== null;
    }
    byId("play").disabled = !ready;
    byId("setup-hint").textContent = t(hint);
    byId("setup-hint").hidden = ready || this.mode === "chess960";
  }

  /** @returns {GameSetup} */
  read() {
    return {
      color: this.color,
      variant_ids: this.mode === "opening" ? [...this.tree.selected] : [],
      from_game:
        this.mode === "saved" && this.savedGameId
          ? {
              game_id: this.savedGameId,
              upto_ply: Number(byId("from-saved-ply").value),
              mode: this.radioValue("from-mode") ?? "line",
            }
          : null,
      chess960: this.mode === "chess960" ? this.chess960 : null,
      level: byId("level").value,
      pace: /** @type {"human" | "instant"} */ (this.radioValue("pace")),
      time_control: byId("time-control").value,
      clock: this.selectedClock(),
      warning: byId("opt-warning").checked,
      premoves: byId("opt-premoves").checked,
    };
  }

  /** @param {GameSetup} setup */
  save(setup) {
    setPref("color", setup.color);
    setPref("level", setup.level);
    setPref("pace", setup.pace);
    setPref("timeControl", setup.time_control);
    setPref("warning", setup.warning);
    setPref("premoves", setup.premoves);
  }
}
