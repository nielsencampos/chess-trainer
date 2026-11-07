// The setup card: color, openings and variations, level, clock, pace, options.

import { localizedName, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

export const TIME_CONTROLS = {
  "3+2": { base_ms: 180_000, increment_ms: 2_000 },
  "10+5": { base_ms: 600_000, increment_ms: 5_000 },
  "15+10": { base_ms: 900_000, increment_ms: 10_000 },
  "45+30": { base_ms: 2_700_000, increment_ms: 30_000 },
  none: null,
};

/**
 * @typedef {{variant_id: string, names: Record<string, string>, eco: string | null}} VariantInfo
 * @typedef {{repertoire_id: string, color: string, names: Record<string, string>, variants: VariantInfo[]}} RepertoireInfo
 * @typedef {{
 *   color: "white" | "black", variant_ids: string[], level: string, pace: "human" | "instant",
 *   time_control: string, scoresheet: boolean, warning: boolean, autoplay: boolean,
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
   * @param {(color: "white" | "black") => void} onColorChange
   * @param {(setup: GameSetup) => void} onPlay
   */
  constructor(repertoires, levels, defaultLevel, onColorChange, onPlay) {
    this.repertoires = repertoires;
    this.onColorChange = onColorChange;
    /** @type {Set<string>} */
    this.unselected = new Set(getPref("unselected", []));

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
        this.renderOpenings();
        this.onColorChange(this.color);
      });
    }
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
    return document.querySelector(`input[name="${name}"]:checked`)?.value;
  }

  /** @returns {"white" | "black"} */
  get color() {
    return /** @type {"white" | "black"} */ (this.radioValue("color"));
  }

  renderOpenings() {
    const container = byId("openings");
    container.replaceChildren();
    const openState = new Set(getPref("openRepertoires", []));
    for (const repertoire of this.repertoires) {
      if (repertoire.color !== this.color) continue;
      container.append(this.openingElement(repertoire, openState.has(repertoire.repertoire_id)));
    }
    this.updatePlay();
  }

  /**
   * @param {RepertoireInfo} repertoire
   * @param {boolean} isOpen
   */
  openingElement(repertoire, isOpen) {
    const details = document.createElement("details");
    details.className = "opening";
    details.dataset.repertoire = repertoire.repertoire_id;
    details.open = isOpen;
    details.addEventListener("toggle", () => this.saveOpenState());

    const summary = document.createElement("summary");
    const all = document.createElement("input");
    all.type = "checkbox";
    all.className = "opening-check";
    all.setAttribute("aria-label", localizedName(repertoire.names));
    const name = document.createElement("span");
    name.textContent = localizedName(repertoire.names);
    const count = document.createElement("span");
    count.className = "opening-count";
    summary.append(all, name, count);

    const list = document.createElement("div");
    list.className = "variants";
    /** @type {HTMLInputElement[]} */
    const boxes = [];
    const refresh = () => {
      const selected = boxes.filter((box) => box.checked).length;
      all.checked = selected === boxes.length;
      all.indeterminate = selected > 0 && selected < boxes.length;
      count.textContent = t("setup.selectedCount", { selected, total: boxes.length });
    };
    for (const variant of repertoire.variants) {
      const label = document.createElement("label");
      label.className = "variant";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.value = variant.variant_id;
      box.checked = !this.unselected.has(variant.variant_id);
      box.addEventListener("change", () => {
        this.toggle(variant.variant_id, box.checked);
        refresh();
      });
      const text = document.createElement("span");
      text.textContent = localizedName(variant.names);
      const eco = document.createElement("span");
      eco.className = "variant-eco";
      eco.textContent = variant.eco ?? "";
      label.append(box, text, eco);
      list.append(label);
      boxes.push(box);
    }
    all.addEventListener("click", (event) => event.stopPropagation());
    all.addEventListener("change", () => {
      for (const box of boxes) {
        box.checked = all.checked;
        this.toggle(box.value, all.checked);
      }
      refresh();
    });
    refresh();
    details.append(summary, list);
    return details;
  }

  /**
   * @param {string} variantId
   * @param {boolean} selected
   */
  toggle(variantId, selected) {
    if (selected) this.unselected.delete(variantId);
    else this.unselected.add(variantId);
    setPref("unselected", [...this.unselected]);
    this.updatePlay();
  }

  saveOpenState() {
    const open = [...document.querySelectorAll(".opening[open]")].map(
      (element) => /** @type {HTMLElement} */ (element).dataset.repertoire,
    );
    setPref("openRepertoires", open);
  }

  selectedVariantIds() {
    return this.repertoires
      .filter((repertoire) => repertoire.color === this.color)
      .flatMap((repertoire) => repertoire.variants)
      .map((variant) => variant.variant_id)
      .filter((id) => !this.unselected.has(id));
  }

  updatePlay() {
    const hasSelection = this.selectedVariantIds().length > 0;
    byId("play").disabled = !hasSelection;
    byId("setup-hint").hidden = hasSelection;
  }

  /** @returns {GameSetup} */
  read() {
    return {
      color: this.color,
      variant_ids: this.selectedVariantIds(),
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
