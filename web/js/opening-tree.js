// The book's tree: group > opening > subgroup > line, with a search and checkboxes. New Game uses
// it to choose what to train, and Openings to view and export lines. The whole catalog is listed,
// so families render their lines only when opened.

import { localizedName, t } from "./i18n.js";

const SEARCH_DEBOUNCE_MS = 150;
const GROUPS = ["kings-pawn", "queens-pawn", "flank", "others"];
const MAX_SEARCH_RESULTS_PER_FAMILY = 200;

/**
 * @typedef {import("./setup.js").VariantInfo} VariantInfo
 * @typedef {import("./setup.js").RepertoireInfo} RepertoireInfo
 * @typedef {{
 *   search: HTMLInputElement, container: HTMLElement, total: HTMLElement,
 *   selectAll: HTMLElement, clear: HTMLElement, noMatches: HTMLElement,
 * }} TreeElements
 */

/**
 * Whether a line matches a search, by name, catalog name, ECO or moves.
 * @param {VariantInfo} variant  The line.
 * @param {string} query  The search, lowercase.
 * @returns {boolean} True if it matches.
 */
function matches(variant, query) {
  return [localizedName(variant.names), variant.opening, variant.eco, variant.pgn].some((text) =>
    text?.toLowerCase().includes(query),
  );
}

/** The book's tree with a search and checkboxes, shared by New Game and Openings. */
export class OpeningTree {
  /**
   * Builds the tree and wires the search, Select all and Clear.
   * @param {RepertoireInfo[]} repertoires  Already in the book's order.
   * @param {TreeElements} els  The search field, the tree's container and its controls.
   * @param {string[]} selected  The line ids ticked at the start.
   * @param {(selected: Set<string>) => void} onChange  Called after every change of the ticks.
   * @param {(variantId: string) => void} [onView]  Gives each line a button to view it.
   */
  constructor(repertoires, els, selected, onChange, onView) {
    this.repertoires = repertoires;
    this.els = els;
    this.selected = new Set(selected);
    this.onChange = onChange;
    this.onView = onView;
    /** @type {{all: HTMLInputElement, count: HTMLElement, variants: VariantInfo[]}[]} */
    this.nodes = [];
    /** @type {HTMLInputElement[]} */
    this.boxes = [];
    /** @type {Set<string> | null} While drawing again, the levels that were open. */
    this.reopen = null;
    // The field is usable before the book arrives, so it may already have text.
    this.query = els.search.value.trim().toLowerCase();

    let debounce = 0;
    els.search.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        this.query = els.search.value.trim().toLowerCase();
        this.render();
      }, SEARCH_DEBOUNCE_MS);
    });
    els.selectAll.addEventListener("click", () => {
      for (const repertoire of this.repertoires) {
        for (const variant of this.shownVariants(repertoire)) {
          this.selected.add(variant.variant_id);
        }
      }
      this.changed();
    });
    els.clear.addEventListener("click", () => {
      this.selected.clear();
      this.changed();
      this.render();
    });
    this.render();
  }

  /** Writes how many lines are ticked, and shows Clear when there are any. */
  renderTotal() {
    this.els.total.textContent = t("setup.selectedTotal", { count: this.selected.size });
    this.els.clear.hidden = this.selected.size === 0;
  }

  /** Updates every checkbox and count after the ticks changed, and reports it. */
  changed() {
    for (const node of this.nodes) this.refreshNode(node);
    for (const box of this.boxes) box.checked = this.selected.has(box.value);
    this.renderTotal();
    this.onChange(this.selected);
  }

  /** Draws the tree again in the language just chosen, keeping what was open. */
  relocalize() {
    const open = this.els.container.querySelectorAll("details[open]");
    this.reopen = new Set([...open].map((details) => /** @type {HTMLElement} */ (details).dataset.key ?? ""));
    try {
      this.render();
    } finally {
      this.reopen = null;
    }
  }

  /** Draws the groups that have lines matching the search. */
  render() {
    this.nodes = [];
    this.boxes = [];
    const container = this.els.container;
    const elements = [];
    for (const group of GROUPS) {
      const members = this.repertoires
        .filter((repertoire) => repertoire.group === group)
        .map((repertoire) => ({ repertoire, shown: this.shownVariants(repertoire) }))
        .filter((item) => item.shown.length > 0);
      if (members.length === 0) continue;
      const main = members.filter((item) => item.repertoire.order !== null);
      const rest = members.filter((item) => item.repertoire.order === null);
      /**
       * Builds a group's families, the less common ones under "Others".
       * @returns {HTMLElement[]} The levels.
       */
      const children = () => {
        const list = main.map((item) => this.openingNode(item.repertoire, item.shown));
        if (main.length > 0 && rest.length > 0) {
          list.push(
            this.treeNode(
              `others:${group}`,
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
        `group:${group}`,
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
    this.els.noMatches.hidden = elements.length > 0;
    this.renderTotal();
  }

  /**
   * A family's lines that match the search; all of them when its own name matches.
   * @param {RepertoireInfo} repertoire  The family.
   * @returns {VariantInfo[]} The lines.
   */
  shownVariants(repertoire) {
    const familyMatches = localizedName(repertoire.names).toLowerCase().includes(this.query);
    return this.query && !familyMatches
      ? repertoire.variants.filter((variant) => matches(variant, this.query))
      : repertoire.variants;
  }

  /**
   * A family's level, whose subgroups are built when first opened.
   * @param {RepertoireInfo} repertoire  The family.
   * @param {VariantInfo[]} shown  Its lines that match the search.
   * @returns {HTMLDetailsElement} The level.
   */
  openingNode(repertoire, shown) {
    const details = this.treeNode(
      `rep:${repertoire.repertoire_id}`,
      localizedName(repertoire.names),
      shown,
      () => this.subgroupNodes(repertoire.repertoire_id, shown),
      "opening",
      false,
      true,
    );
    details.dataset.repertoire = repertoire.repertoire_id;
    return details;
  }

  /**
   * A family's subgroups, then its loose lines under "Others"; only lines if it has no subgroups.
   * @param {string} repertoireId  The family id.
   * @param {VariantInfo[]} shown  Its lines that match the search.
   * @returns {HTMLElement[]} The levels or lines.
   */
  subgroupNodes(repertoireId, shown) {
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
    /** Builds the rows of some lines later, when their level opens. */
    const lines = (/** @type {VariantInfo[]} */ list) => () =>
      list.map((variant) => this.variantElement(variant));
    const nodes = [...groups].map(([name, list]) =>
      this.treeNode(`sub:${repertoireId}:${list[0].subgroup?.en ?? name}`, name, list, lines(list), "tree-variant"),
    );
    if (groups.size === 0) return lines(loose)();
    if (loose.length > 0) {
      nodes.push(this.treeNode(`sub:${repertoireId}:`, t("tree.others"), loose, lines(loose), "tree-variant"));
    }
    return nodes;
  }

  /**
   * One collapsible level, with a checkbox for everything inside it.
   * @param {string} key  Stays the same in every language, to keep the level open when redrawn.
   * @param {string} label  The level's name.
   * @param {VariantInfo[]} variants  Every line inside it.
   * @param {() => HTMLElement[]} children  Builds what is inside.
   * @param {string} className  The level's kind, such as `tree-group` or `opening`.
   * @param {boolean} [startOpen]  Opens it at once.
   * @param {boolean} [lazy]  Builds what is inside only when first opened.
   * @returns {HTMLDetailsElement} The level.
   */
  treeNode(key, label, variants, children, className, startOpen = false, lazy = false) {
    const details = document.createElement("details");
    details.dataset.key = key;
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
    /** Builds the level's content once. */
    const build = () => {
      if (!list.hasChildNodes()) list.append(...children());
    };
    all.addEventListener("click", (event) => event.stopPropagation());
    all.addEventListener("change", () => {
      for (const variant of variants) {
        if (all.checked) this.selected.add(variant.variant_id);
        else this.selected.delete(variant.variant_id);
      }
      this.changed();
    });
    details.addEventListener("toggle", () => {
      if (details.open) build();
    });
    this.nodes.push({ all, count, variants });
    this.refreshNode({ all, count, variants });
    details.append(summary, list);
    if (!lazy) build();
    // Show results right away when a search narrowed things down.
    const open = this.reopen
      ? this.reopen.has(key)
      : startOpen || (this.query && variants.length <= MAX_SEARCH_RESULTS_PER_FAMILY);
    if (open) {
      build();
      details.open = true;
    }
    return details;
  }

  /**
   * Updates a level's checkbox and its ticked count.
   * @param {{all: HTMLInputElement, count: HTMLElement, variants: VariantInfo[]}} node  The level.
   * @returns {void}
   */
  refreshNode({ all, count, variants }) {
    const selected = variants.filter((variant) => this.selected.has(variant.variant_id)).length;
    all.checked = selected === variants.length;
    all.indeterminate = selected > 0 && selected < variants.length;
    count.textContent = t("setup.selectedCount", { selected, total: variants.length });
  }

  /**
   * One line: checkbox, name, moves, ECO and, in Openings, View.
   * @param {VariantInfo} variant  The line.
   * @returns {HTMLLabelElement} The row.
   */
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
      this.changed();
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
    label.append(box, text, eco);
    if (this.onView) {
      const view = document.createElement("button");
      view.type = "button";
      view.className = "view-button";
      view.textContent = t("review.view");
      view.addEventListener("click", (event) => {
        event.preventDefault(); // It sits inside the row's label.
        this.onView?.(variant.variant_id);
      });
      label.append(view);
    }
    return label;
  }
}
