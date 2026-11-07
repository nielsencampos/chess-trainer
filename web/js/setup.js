// The setup card: color, openings and variations, level, clock, pace, options.
// The whole catalog is selectable, so families render their lines only when opened.

import { api } from "./api.js";
import { localizedName, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

const SEARCH_DEBOUNCE_MS = 150;
const GROUPS = ["kings-pawn", "queens-pawn", "flank", "others"];
const MAX_SEARCH_RESULTS_PER_FAMILY = 200;

/**
 * @typedef {{variant_id: string, names: Record<string, string>, eco: string | null,
 *   opening: string | null, pgn: string, subgroup: Record<string, string> | null}} VariantInfo
 * @typedef {{repertoire_id: string, names: Record<string, string>, group: string,
 *   order: number | null, variants: VariantInfo[]}} RepertoireInfo
 * @typedef {{key: string, base_ms: number, increment_ms: number,
 *   periods: {after_moves: number, add_ms: number}[],
 *   delay_ms: number, delay_kind: string | null}} TimeControlInfo
 * @typedef {{key: string, scoresheet: boolean, items: TimeControlInfo[]}} TimeControlGroup
 * @typedef {{groups: TimeControlGroup[], no_clock: string, default: string}} TimeControls
 * @typedef {{
 *   color: "white" | "black", variant_ids: string[], level: string, pace: "human" | "instant",
 *   time_control: string, clock: TimeControlInfo | null,
 *   from_game?: {game_id: string, upto_ply: number, mode: string} | null,
 *   scoresheet: boolean, warning: boolean, autoplay: boolean, premoves: boolean,
 * }} GameSetup
 */

/** @param {string} selector */
const radios = (selector) => /** @type {NodeListOf<HTMLInputElement>} */ (document.querySelectorAll(selector));

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/**
 * @param {VariantInfo} variant
 * @param {string} query  Lowercase.
 */
function matches(variant, query) {
  return [variant.opening, variant.eco, variant.pgn].some((text) => text?.toLowerCase().includes(query));
}

export class SetupCard {
  /**
   * @param {RepertoireInfo[]} repertoires
   * @param {string[]} levels
   * @param {string} defaultLevel
   * @param {TimeControls} timeControls
   * @param {(color: "white" | "black") => void} onColorChange
   * @param {(setup: GameSetup) => void} onPlay
   * @param {(variantId: string) => void} onViewLine
   */
  constructor(repertoires, levels, defaultLevel, timeControls, onColorChange, onPlay, onViewLine) {
    this.onViewLine = onViewLine;
    this.repertoires = repertoires; // Already in the book's order.
    /** @type {{all: HTMLInputElement, count: HTMLElement, variants: VariantInfo[]}[]} */
    this.nodes = [];
    /** @type {HTMLInputElement[]} */
    this.boxes = [];
    this.onColorChange = onColorChange;
    const known = new Set(repertoires.flatMap((rep) => rep.variants.map((v) => v.variant_id)));
    /** @type {Set<string>} */
    this.selected = new Set(getPref("selected", []).filter((id) => known.has(id)));
    // The field is usable before the book arrives, so it may already have text.
    this.query = byId("opening-search").value.trim().toLowerCase();

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
    timeSelect.addEventListener("change", () => this.updateScoresheetOption());
    this.updateScoresheetOption();

    this.setRadio("color", getPref("color", "white"));
    this.setRadio("pace", getPref("pace", "human"));
    byId("opt-scoresheet").checked = getPref("scoresheet", false);
    byId("opt-warning").checked = getPref("warning", true);
    byId("opt-autoplay").checked = getPref("autoplay", false);
    byId("opt-premoves").checked = getPref("premoves", true);

    for (const radio of radios('input[name="color"]')) {
      radio.addEventListener("change", () => {
        setPref("color", this.color);
        this.onColorChange(this.color);
      });
    }
    let debounce = 0;
    byId("opening-search").addEventListener("input", (/** @type {any} */ event) => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        this.query = event.target.value.trim().toLowerCase();
        this.renderOpenings();
      }, SEARCH_DEBOUNCE_MS);
    });
    /** @type {"opening" | "saved"} */
    this.mode = "opening";
    /** @type {any[]} */
    this.savedGames = [];
    /** @type {string | null} */
    this.savedGameId = null;
    byId("select-all").addEventListener("click", () => {
      for (const repertoire of this.repertoires) {
        for (const variant of this.shownVariants(repertoire)) {
          this.selected.add(variant.variant_id);
        }
      }
      this.saveSelection();
    });
    byId("from-saved-search").addEventListener("input", () => this.renderSavedGames());
    for (const radio of radios('input[name="from-mode"]')) {
      radio.addEventListener("change", () => this.renderFromSavedHelp());
    }
    this.renderFromSavedHelp();
    byId("clear-selection").addEventListener("click", () => {
      this.selected.clear();
      this.saveSelection();
      this.renderOpenings();
    });
    byId("play").addEventListener("click", () => {
      const setup = this.read();
      this.save(setup);
      onPlay(setup);
    });
    this.renderOpenings();
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
    return `${t("setup.tc.minutes", { minutes })}${extra}`;
  }

  /** @param {string} key */
  timeLabelFor(key) {
    const item = this.clockFor(key);
    return item ? this.timeLabel(item) : key;
  }

  /** Scoresheet mode exists only where moves are written on paper. */
  allowsScoresheet() {
    const key = byId("time-control").value;
    if (key === this.timeControls.no_clock) return true;
    return this.timeControls.groups.some(
      (group) => group.scoresheet && group.items.some((item) => item.key === key),
    );
  }

  updateScoresheetOption() {
    byId("scoresheet-option").hidden = !this.allowsScoresheet();
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

  renderOpenings() {
    this.nodes = [];
    this.boxes = [];
    const container = byId("openings");
    const elements = [];
    for (const group of GROUPS) {
      const members = this.repertoires
        .filter((repertoire) => repertoire.group === group)
        .map((repertoire) => ({ repertoire, shown: this.shownVariants(repertoire) }))
        .filter((item) => item.shown.length > 0);
      if (members.length === 0) continue;
      const main = members.filter((item) => item.repertoire.order !== null);
      const rest = members.filter((item) => item.repertoire.order === null);
      const children = () => {
        const list = main.map((item) => this.openingNode(item.repertoire, item.shown));
        if (main.length > 0 && rest.length > 0) {
          list.push(
            this.treeNode(
              t("tree.others"),
              rest.flatMap((item) => item.shown),
              () => rest.map((item) => this.openingNode(item.repertoire, item.shown)),
              "tree-others",
            ),
          );
        } else {
          list.push(...rest.map((item) => this.openingNode(item.repertoire, item.shown)));
        }
        return list;
      };
      const node = this.treeNode(
        t(`tree.group.${group}`),
        members.flatMap((item) => item.shown),
        children,
        "tree-group",
        true,
      );
      node.dataset.group = group;
      elements.push(node);
    }
    container.replaceChildren(...elements);
    byId("no-matches").hidden = elements.length > 0;
    this.updateSelectionState();
  }

  /** @param {RepertoireInfo} repertoire */
  shownVariants(repertoire) {
    const familyMatches = localizedName(repertoire.names).toLowerCase().includes(this.query);
    return this.query && !familyMatches
      ? repertoire.variants.filter((variant) => matches(variant, this.query))
      : repertoire.variants;
  }

  /**
   * @param {RepertoireInfo} repertoire
   * @param {VariantInfo[]} shown
   */
  openingNode(repertoire, shown) {
    const details = this.treeNode(
      localizedName(repertoire.names),
      shown,
      () => this.subgroupNodes(shown),
      "opening",
      false,
      true,
    );
    details.dataset.repertoire = repertoire.repertoire_id;
    return details;
  }

  /** @param {VariantInfo[]} shown */
  subgroupNodes(shown) {
    /** @type {Map<string, VariantInfo[]>} */
    const groups = new Map();
    /** @type {VariantInfo[]} */
    const loose = [];
    for (const variant of shown) {
      if (!variant.subgroup) {
        loose.push(variant);
        continue;
      }
      const name = localizedName(variant.subgroup);
      groups.set(name, [...(groups.get(name) ?? []), variant]);
    }
    const lines = (/** @type {VariantInfo[]} */ list) => () =>
      list.map((variant) => this.variantElement(variant));
    const nodes = [...groups].map(([name, list]) =>
      this.treeNode(name, list, lines(list), "tree-variant"),
    );
    if (groups.size === 0) return lines(loose)();
    if (loose.length > 0) {
      nodes.push(this.treeNode(t("tree.others"), loose, lines(loose), "tree-variant"));
    }
    return nodes;
  }

  /**
   * One collapsible level, with a checkbox for everything inside it.
   * @param {string} label
   * @param {VariantInfo[]} variants
   * @param {() => HTMLElement[]} children
   * @param {string} className
   * @param {boolean} [startOpen]
   * @param {boolean} [lazy]  Builds what is inside only when first opened.
   */
  treeNode(label, variants, children, className, startOpen = false, lazy = false) {
    const details = document.createElement("details");
    details.className = `tree-node ${className}`;
    const summary = document.createElement("summary");
    const all = document.createElement("input");
    all.type = "checkbox";
    all.className = className === "opening" ? "opening-check" : "tree-check";
    all.setAttribute("aria-label", label);
    const name = document.createElement("span");
    name.className = "opening-name";
    name.textContent = label;
    const count = document.createElement("span");
    count.className = "opening-count";
    summary.append(all, name, count);

    const list = document.createElement("div");
    list.className = "tree-children";
    const build = () => {
      if (!list.hasChildNodes()) list.append(...children());
    };
    all.addEventListener("click", (event) => event.stopPropagation());
    all.addEventListener("change", () => {
      for (const variant of variants) {
        if (all.checked) this.selected.add(variant.variant_id);
        else this.selected.delete(variant.variant_id);
      }
      this.saveSelection();
    });
    details.addEventListener("toggle", () => {
      if (details.open) build();
    });
    this.nodes.push({ all, count, variants });
    this.refreshNode({ all, count, variants });
    details.append(summary, list);
    if (!lazy) build();
    // Show results right away when a search narrowed things down.
    if (startOpen || (this.query && variants.length <= MAX_SEARCH_RESULTS_PER_FAMILY)) {
      build();
      details.open = true;
    }
    return details;
  }

  /** @param {{all: HTMLInputElement, count: HTMLElement, variants: VariantInfo[]}} node */
  refreshNode({ all, count, variants }) {
    const selected = variants.filter((variant) => this.selected.has(variant.variant_id)).length;
    all.checked = selected === variants.length;
    all.indeterminate = selected > 0 && selected < variants.length;
    count.textContent = t("setup.selectedCount", { selected, total: variants.length });
  }

  /** @param {VariantInfo} variant */
  variantElement(variant) {
    const label = document.createElement("label");
    label.className = "variant";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = variant.variant_id;
    box.checked = this.selected.has(variant.variant_id);
    box.addEventListener("change", () => {
      if (box.checked) this.selected.add(variant.variant_id);
      else this.selected.delete(variant.variant_id);
      this.saveSelection();
    });
    this.boxes.push(box);
    const text = document.createElement("span");
    text.className = "variant-text";
    const name = document.createElement("span");
    name.textContent = localizedName(variant.names);
    const moves = document.createElement("span");
    moves.className = "variant-moves";
    moves.textContent = variant.pgn;
    text.append(name, moves);
    const eco = document.createElement("span");
    eco.className = "variant-eco";
    eco.textContent = variant.eco ?? "";
    const view = document.createElement("button");
    view.type = "button";
    view.className = "view-button";
    view.textContent = t("review.view");
    view.addEventListener("click", (event) => {
      event.preventDefault(); // It sits inside the row's label.
      this.onViewLine(variant.variant_id);
    });
    label.append(box, text, eco, view);
    return label;
  }

  saveSelection() {
    setPref("selected", [...this.selected]);
    for (const node of this.nodes) this.refreshNode(node);
    for (const box of this.boxes) box.checked = this.selected.has(box.value);
    this.updateSelectionState();
  }

  /** @param {"opening" | "saved"} mode */
  async setMode(mode) {
    this.mode = mode;
    byId("openings-field").hidden = mode !== "opening";
    byId("from-saved").hidden = mode !== "saved";
    this.updateSelectionState();
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
    if (this.mode === "saved") {
      const ready = this.savedGameId !== null;
      byId("play").disabled = !ready;
      byId("setup-hint").hidden = ready;
      byId("setup-hint").textContent = t("setup.selectGame");
      return;
    }
    byId("setup-hint").textContent = t("setup.selectOne");
    const total = this.selected.size;
    byId("selected-total").textContent = t("setup.selectedTotal", { count: total });
    byId("clear-selection").hidden = total === 0;
    byId("play").disabled = total === 0;
    byId("setup-hint").hidden = total > 0;
  }

  /** @returns {GameSetup} */
  read() {
    return {
      color: this.color,
      variant_ids: this.mode === "opening" ? [...this.selected] : [],
      from_game:
        this.mode === "saved" && this.savedGameId
          ? {
              game_id: this.savedGameId,
              upto_ply: Number(byId("from-saved-ply").value),
              mode: this.radioValue("from-mode") ?? "line",
            }
          : null,
      level: byId("level").value,
      pace: /** @type {"human" | "instant"} */ (this.radioValue("pace")),
      time_control: byId("time-control").value,
      clock: this.selectedClock(),
      scoresheet: this.allowsScoresheet() && byId("opt-scoresheet").checked,
      warning: byId("opt-warning").checked,
      autoplay: byId("opt-autoplay").checked,
      premoves: byId("opt-premoves").checked,
    };
  }

  /** @param {GameSetup} setup */
  save(setup) {
    setPref("color", setup.color);
    setPref("level", setup.level);
    setPref("pace", setup.pace);
    setPref("timeControl", setup.time_control);
    setPref("scoresheet", byId("opt-scoresheet").checked);
    setPref("warning", setup.warning);
    setPref("autoplay", setup.autoplay);
    setPref("premoves", setup.premoves);
  }
}
