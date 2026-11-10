// The "Saved games" and "Import games" screens, and the menu that switches between screens
// (Help and Scoresheet show in the board area, see pages.js):
// finished games, filters, selection, export, deletion and imports.

import { ApiError, api } from "./api.js";
import { getLocale, localize, onLocaleChange, t } from "./i18n.js";
import { openingName, openingSearchText } from "./opening-names.js";
import { showPage } from "./pages.js";

/**
 * Finds an element by id.
 * @param {string} id  The element's id.
 * @returns {any} The element.
 */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/**
 * @typedef {{game_id: string, started_at: string, user_color: string, time_control: string,
 *   level: string, result: string, termination: string, eco: string | null,
 *   opening: string | null, plies: number, source: string,
 *   white: string | null, black: string | null}} SavedGame
 */

const TABS = ["new", "saved", "openings", "import", "scoresheet", "help"];
/** The tabs whose screen is a page in the board area, and that page. */
const PAGES = /** @type {Record<string, string>} */ ({ help: "help", scoresheet: "sheet" });
const DELETE_CONFIRM_MS = 3000;

/** The Saved games list and the imports, and the menu tabs that show one screen at a time. */
export class SavedGames {
  /**
   * Wires the menu tabs, the list's filters and buttons, and the import forms.
   * @param {(key: string) => string} timeLabel  The label of a time control key.
   * @param {import("./setup.js").SetupCard} setup  The New Game card, shown by its tab.
   * @param {(gameId: string) => void} onView  Opens a saved game's review.
   * @param {() => void} onLeaveTab  Leaves a review or a finished game when a tab is clicked.
   */
  constructor(timeLabel, setup, onView, onLeaveTab) {
    this.onLeaveTab = onLeaveTab;
    this.deleteTimer = 0;
    this.timeLabel = timeLabel;
    this.setup = setup;
    this.onView = onView;
    /** @type {SavedGame[]} */
    this.games = [];
    /** @type {Set<string>} */
    this.selected = new Set();

    // The tabs start disabled, so a click made while the page loads is not lost.
    for (const tab of TABS) {
      byId(`tab-${tab}`).addEventListener("click", () => this.showTab(tab));
      byId(`tab-${tab}`).disabled = false;
    }
    for (const id of ["saved-search", "saved-color", "saved-result"]) {
      byId(id).addEventListener("input", () => this.render());
    }
    byId("saved-select-all").addEventListener("change", (/** @type {any} */ event) => {
      for (const game of this.visibleGames()) {
        if (event.target.checked) this.selected.add(game.game_id);
        else this.selected.delete(game.game_id);
      }
      this.render();
    });
    byId("saved-export").addEventListener("click", () => void this.exportSelected());
    byId("saved-delete").addEventListener("click", () => this.onDeleteClick());
    byId("import-paste").addEventListener("click", () => {
      void this.importText(byId("import-text").value);
    });
    byId("import-remote").addEventListener("submit", (/** @type {Event} */ event) => {
      event.preventDefault();
      void this.importRemote();
    });
    byId("import-file").addEventListener("change", async (/** @type {any} */ event) => {
      const [file] = event.target.files;
      event.target.value = ""; // So the same file can be chosen again.
      if (file) await this.importText(await file.text());
    });
    onLocaleChange(() => this.render());
  }

  /**
   * The error line under the list. It is written through `localize`, so it follows the language.
   * @param {string} key  The message's i18n key.
   * @returns {void}
   */
  showError(key) {
    localize(byId("saved-error"), () => {
      byId("saved-error").textContent = t(key);
    });
    byId("saved-error").hidden = false;
  }

  /**
   * Shows one screen of the menu and marks its tab.
   * @param {string} tab  `new`, `saved`, `openings`, `import`, `scoresheet` or `help`.
   * @returns {void}
   */
  showTab(tab) {
    this.onLeaveTab();
    byId("setup-card").hidden = tab !== "new";
    byId("openings-card").hidden = tab !== "openings";
    byId("saved-card").hidden = tab !== "saved";
    byId("import-card").hidden = tab !== "import";
    showPage(PAGES[tab] ?? null);
    for (const name of TABS) {
      byId(`tab-${name}`).classList.toggle("active", tab === name);
    }
    this.setup.setShown(tab === "new");
    if (tab === "new") void this.setup.setMode(this.setup.mode);
    if (tab === "saved") void this.load();
  }

  /**
   * Reloads the saved games, keeping the selection of those that still exist.
   * @returns {Promise<void>}
   */
  async load() {
    byId("saved-error").hidden = true;
    try {
      this.games = (await api.savedGames()).games;
    } catch (error) {
      console.error(error);
      this.games = [];
      this.showError("saved.loadError");
    }
    const known = new Set(this.games.map((game) => game.game_id));
    this.selected = new Set([...this.selected].filter((id) => known.has(id)));
    this.render();
  }

  /**
   * Imports pasted or uploaded PGN, and clears the box when every game went in.
   * @param {string} text  The PGN.
   * @returns {Promise<void>}
   */
  async importText(text) {
    this.startImport("import");
    let report;
    try {
      report = await api.importGames(text);
    } catch (error) {
      console.error(error);
      this.setSummary("import", () => t("import.failed"));
      return;
    }
    await this.showImport(report, "import");
    if (report.errors.length === 0 && report.imported > 0) byId("import-text").value = "";
  }

  /**
   * Fetches a player's games from Lichess or Chess.com and imports them.
   * @returns {Promise<void>}
   */
  async importRemote() {
    const button = byId("import-fetch");
    const site = /** @type {"lichess" | "chesscom"} */ (byId("import-site").value);
    const username = byId("import-username").value.trim();
    this.startImport("import-remote");
    this.setSummary("import-remote", () => t("import.remote.busy"));
    button.disabled = true;
    try {
      const report = await api.importRemote(site, username, Number(byId("import-months").value));
      await this.showImport(report, "import-remote");
    } catch (error) {
      console.error(error);
      const code = error instanceof ApiError ? error.code : undefined;
      this.setSummary("import-remote", () => (code ? t(`import.remote.error.${code}`) : t("import.failed")));
    } finally {
      button.disabled = false;
    }
  }

  /**
   * Clears a form's errors and shows its summary line.
   * @param {"import" | "import-remote"} prefix  Which form: the paste and file one, or the site one.
   * @returns {void}
   */
  startImport(prefix) {
    this.setErrors(prefix, []);
    byId(`${prefix}-summary`).hidden = false;
  }

  /**
   * Writes a form's summary, through `localize` so it follows the language.
   * @param {"import" | "import-remote"} prefix  Which form: the paste and file one, or the site one.
   * @param {() => string} text  Builds the summary in the current language.
   * @returns {void}
   */
  setSummary(prefix, text) {
    const summary = byId(`${prefix}-summary`);
    localize(summary, () => {
      summary.textContent = text();
    });
  }

  /**
   * Lists the refused games of an import, through `localize` so it follows the language.
   * @param {"import" | "import-remote"} prefix  Which form: the paste and file one, or the site one.
   * @param {any[]} items  The report's errors.
   * @returns {void}
   */
  setErrors(prefix, items) {
    const errors = byId(`${prefix}-errors`);
    localize(errors, () => {
      errors.replaceChildren(
        ...items.map((item) => {
          const line = document.createElement("li");
          line.textContent = t("import.errorLine", {
            index: item.index,
            label: item.label,
            reason: t(`import.error.${item.code}`),
          });
          return line;
        }),
      );
    });
  }

  /**
   * Shows an import's report, then reloads the list.
   * @param {{imported: number, duplicates: number, updated?: number, errors: any[],
   *   fetched?: number, truncated?: boolean}} report  The API's import report.
   * @param {"import" | "import-remote"} prefix  Which form: the paste and file one, or the site one.
   * @returns {Promise<void>}
   */
  async showImport(report, prefix) {
    const total =
      report.imported + report.duplicates + (report.updated ?? 0) + report.errors.length;
    this.setSummary(prefix, () => {
      let text = total === 0
        ? t(report.fetched === undefined ? "import.nothing" : "import.remote.nothing")
        : t("import.summary", {
            imported: report.imported,
            duplicates: report.duplicates,
            failed: report.errors.length,
          });
      if (report.updated) text += ` ${t("import.updated", { updated: report.updated })}`;
      if (report.truncated) text += ` ${t("import.remote.truncated", { max: report.fetched ?? 0 })}`;
      return text;
    });
    this.setErrors(prefix, report.errors);
    await this.load();
  }

  /**
   * The games that pass the search, color and result filters.
   * @returns {SavedGame[]} The games, newest first.
   */
  visibleGames() {
    const query = byId("saved-search").value.trim().toLowerCase();
    const color = byId("saved-color").value;
    const result = byId("saved-result").value;
    return this.games.filter(
      (game) =>
        (!color || game.user_color === color) &&
        (!result || game.result === result) &&
        (!query || openingSearchText(game).includes(query)),
    );
  }

  /** Draws the list, the select-all box, the count and the buttons. */
  render() {
    const visible = this.visibleGames();
    byId("saved-list").replaceChildren(...visible.map((game) => this.row(game)));
    byId("saved-empty").hidden = visible.length > 0;
    byId("saved-empty").textContent = t(this.games.length ? "saved.noMatches" : "saved.none");

    const selectedVisible = visible.filter((game) => this.selected.has(game.game_id)).length;
    const all = byId("saved-select-all");
    all.checked = visible.length > 0 && selectedVisible === visible.length;
    all.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;
    byId("saved-count").textContent = t("saved.count", { count: visible.length });
    const exportButton = byId("saved-export");
    exportButton.disabled = this.selected.size === 0;
    exportButton.textContent = t("saved.export", { count: this.selected.size });
    this.resetDelete();
  }

  /** Deleting needs a second click within 3 s, like resigning; it cannot be undone. */
  onDeleteClick() {
    const button = byId("saved-delete");
    if (!button.classList.contains("confirming")) {
      button.classList.add("confirming");
      button.textContent = t("saved.deleteConfirm", { count: this.selected.size });
      this.deleteTimer = setTimeout(() => this.resetDelete(), DELETE_CONFIRM_MS);
      return;
    }
    void this.deleteSelected();
  }

  /** Puts the Delete button back to its first state, with the selection's count. */
  resetDelete() {
    clearTimeout(this.deleteTimer);
    const button = byId("saved-delete");
    button.classList.remove("confirming");
    button.disabled = this.selected.size === 0;
    button.textContent = t("saved.delete", { count: this.selected.size });
  }

  /**
   * Deletes the selected games for good, then reloads the list.
   * @returns {Promise<void>}
   */
  async deleteSelected() {
    byId("saved-error").hidden = true;
    try {
      await api.deleteGames([...this.selected]);
      this.selected.clear();
    } catch (error) {
      console.error(error);
      this.showError("saved.deleteError");
    }
    await this.load();
  }

  /**
   * One row of the list: checkbox, opening, details, result and View.
   * @param {SavedGame} game  The game.
   * @returns {HTMLLabelElement} The row.
   */
  row(game) {
    const label = document.createElement("label");
    label.className = "saved-game";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = game.game_id;
    box.checked = this.selected.has(game.game_id);
    box.addEventListener("change", () => {
      if (box.checked) this.selected.add(game.game_id);
      else this.selected.delete(game.game_id);
      this.render();
    });

    const text = document.createElement("span");
    text.className = "variant-text";
    const name = document.createElement("span");
    const eco = game.eco ? `${game.eco} · ` : "";
    name.textContent = `${eco}${game.opening ? openingName(game.opening) : t("saved.noOpening")}`;
    const details = document.createElement("span");
    details.className = "variant-moves";
    const imported = game.source === "imported";
    details.textContent = (
      imported
        ? [
            t("saved.imported"),
            new Date(game.started_at).toLocaleDateString(getLocale(), { timeZone: "UTC" }),
            `${game.white} - ${game.black}`,
            t("saved.plies", { count: game.plies }),
          ]
        : [
            new Date(game.started_at).toLocaleString(getLocale()),
            t(`setup.${game.user_color}`),
            game.time_control === "none" ? t("setup.noClock") : this.timeLabel(game.time_control),
            t("saved.plies", { count: game.plies }),
          ]
    ).join(" · ");
    text.append(name, details);

    const result = document.createElement("span");
    result.className = `saved-result saved-result-${imported ? "imported" : game.result}`;
    result.textContent = imported ? game.result : t(`saved.result.${game.result}`);
    const view = document.createElement("button");
    view.type = "button";
    view.className = "view-button";
    view.textContent = t("review.view");
    view.addEventListener("click", (event) => {
      event.preventDefault(); // It sits inside the row's label.
      this.onView(game.game_id);
    });
    label.append(box, text, result, view);
    return label;
  }

  /**
   * Downloads the selected games as one PGN file, oldest first.
   * @returns {Promise<void>}
   */
  async exportSelected() {
    byId("saved-error").hidden = true;
    try {
      const blob = await api.exportGames([...this.selected]);
      const date = new Date().toISOString().slice(0, 10);
      const count = this.selected.size;
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = count === 1 ? `chess-trainer-${date}.pgn` : `chess-trainer-${date}-${count}-games.pgn`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      console.error(error);
      this.showError("saved.exportError");
    }
  }
}
