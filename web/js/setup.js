// The setup card: color, openings and variations, level, clock, pace, options.
// The whole catalog is selectable, so families render their lines only when opened.

import { localizedName, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

export const TIME_CONTROLS = {
  "3+2": { base_ms: 180_000, increment_ms: 2_000 },
  "10+5": { base_ms: 600_000, increment_ms: 5_000 },
  "15+10": { base_ms: 900_000, increment_ms: 10_000 },
  "45+30": { base_ms: 2_700_000, increment_ms: 30_000 },
  none: null,
};

const SEARCH_DEBOUNCE_MS = 150;
const MAX_SEARCH_RESULTS_PER_FAMILY = 200;

/**
 * @typedef {{variant_id: string, names: Record<string, string>, eco: string | null,
 *   opening: string | null, pgn: string}} VariantInfo
 * @typedef {{repertoire_id: string, names: Record<string, string>, variants: VariantInfo[]}} RepertoireInfo
 * @typedef {{
 *   color: "white" | "black", variant_ids: string[], level: string, pace: "human" | "instant",
 *   time_control: string, scoresheet: boolean, warning: boolean, autoplay: boolean,
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
   * @param {(color: "white" | "black") => void} onColorChange
   * @param {(setup: GameSetup) => void} onPlay
   */
  constructor(repertoires, levels, defaultLevel, onColorChange, onPlay) {
    this.repertoires = [...repertoires].sort((a, b) =>
      localizedName(a.names).localeCompare(localizedName(b.names)),
    );
    this.onColorChange = onColorChange;
    const known = new Set(repertoires.flatMap((rep) => rep.variants.map((v) => v.variant_id)));
    /** @type {Set<string>} */
    this.selected = new Set(getPref("selected", []).filter((id) => known.has(id)));
    // The field is usable before the book arrives, so it may already have text.
    this.query = byId("opening-search").value.trim().toLowerCase();

    const levelSelect = byId("level");
    for (const key of levels) levelSelect.add(new Option(t(`level.${key}`), key));
    levelSelect.value = getPref("level", defaultLevel);

    const timeSelect = byId("time-control");
    for (const key of Object.keys(TIME_CONTROLS)) {
      timeSelect.add(new Option(key === "none" ? t("setup.noClock") : key, key));
    }
    timeSelect.value = getPref("timeControl", "10+5");

    this.setRadio("color", getPref("color", "white"));
    this.setRadio("pace", getPref("pace", "human"));
    byId("opt-scoresheet").checked = getPref("scoresheet", false);
    byId("opt-warning").checked = getPref("warning", true);
    byId("opt-autoplay").checked = getPref("autoplay", false);

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
    const container = byId("openings");
    const elements = [];
    for (const repertoire of this.repertoires) {
      const familyMatches = localizedName(repertoire.names).toLowerCase().includes(this.query);
      const shown = this.query && !familyMatches
        ? repertoire.variants.filter((variant) => matches(variant, this.query))
        : repertoire.variants;
      if (shown.length > 0) elements.push(this.familyElement(repertoire, shown));
    }
    container.replaceChildren(...elements);
    byId("no-matches").hidden = elements.length > 0;
    this.updateSelectionState();
  }

  /**
   * @param {RepertoireInfo} repertoire
   * @param {VariantInfo[]} shown  The lines the search left; all of them without a search.
   */
  familyElement(repertoire, shown) {
    const details = document.createElement("details");
    details.className = "opening";
    details.dataset.repertoire = repertoire.repertoire_id;

    const summary = document.createElement("summary");
    const all = document.createElement("input");
    all.type = "checkbox";
    all.className = "opening-check";
    all.setAttribute("aria-label", localizedName(repertoire.names));
    const name = document.createElement("span");
    name.className = "opening-name";
    name.textContent = localizedName(repertoire.names);
    const count = document.createElement("span");
    count.className = "opening-count";
    summary.append(all, name, count);

    const list = document.createElement("div");
    list.className = "variants";
    const refresh = () => {
      const selected = shown.filter((variant) => this.selected.has(variant.variant_id)).length;
      all.checked = selected === shown.length;
      all.indeterminate = selected > 0 && selected < shown.length;
      count.textContent = t("setup.selectedCount", { selected, total: shown.length });
    };
    all.addEventListener("click", (event) => event.stopPropagation());
    all.addEventListener("change", () => {
      for (const variant of shown) {
        if (all.checked) this.selected.add(variant.variant_id);
        else this.selected.delete(variant.variant_id);
      }
      for (const box of list.querySelectorAll("input")) box.checked = all.checked;
      this.saveSelection();
      refresh();
    });
    details.addEventListener("toggle", () => {
      if (details.open && !list.hasChildNodes()) {
        list.append(...shown.map((variant) => this.variantElement(variant, refresh)));
      }
    });
    refresh();
    details.append(summary, list);
    // Show results right away when a search narrowed this family down.
    if (this.query && shown.length <= MAX_SEARCH_RESULTS_PER_FAMILY) details.open = true;
    return details;
  }

  /**
   * @param {VariantInfo} variant
   * @param {() => void} refresh
   */
  variantElement(variant, refresh) {
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
      refresh();
    });
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
    label.append(box, text, eco);
    return label;
  }

  saveSelection() {
    setPref("selected", [...this.selected]);
    this.updateSelectionState();
  }

  updateSelectionState() {
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
      variant_ids: [...this.selected],
      level: byId("level").value,
      pace: /** @type {"human" | "instant"} */ (this.radioValue("pace")),
      time_control: byId("time-control").value,
      scoresheet: byId("opt-scoresheet").checked,
      warning: byId("opt-warning").checked,
      autoplay: byId("opt-autoplay").checked,
    };
  }

  /** @param {GameSetup} setup */
  save(setup) {
    setPref("color", setup.color);
    setPref("level", setup.level);
    setPref("pace", setup.pace);
    setPref("timeControl", setup.time_control);
    setPref("scoresheet", setup.scoresheet);
    setPref("warning", setup.warning);
    setPref("autoplay", setup.autoplay);
  }
}
