// The "Saved games" tab: finished games, filters, selection and export.

import { ApiError, api } from "./api.js";
import { t } from "./i18n.js";

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/**
 * @typedef {{game_id: string, started_at: string, user_color: string, time_control: string,
 *   level: string, result: string, termination: string, eco: string | null,
 *   opening: string | null, plies: number, source: string,
 *   white: string | null, black: string | null}} SavedGame
 */

const TABS = ["new", "saved", "openings", "import"];
const DELETE_CONFIRM_MS = 3000;

export class SavedGames {
  /**
   * @param {(key: string) => string} timeLabel
   * @param {import("./setup.js").SetupCard} setup
   * @param {(gameId: string) => void} onView
   * @param {() => void} onLeaveTab
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

    for (const tab of TABS) {
      byId(`tab-${tab}`).addEventListener("click", () => this.showTab(tab));
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
  }

  /** @param {string} tab */
  showTab(tab) {
    this.onLeaveTab();
    byId("setup-card").hidden = tab !== "new";
    byId("openings-card").hidden = tab !== "openings";
    byId("saved-card").hidden = tab !== "saved";
    byId("import-card").hidden = tab !== "import";
    for (const name of TABS) {
      byId(`tab-${name}`).classList.toggle("active", tab === name);
    }
    this.setup.setShown(tab === "new");
    if (tab === "new") void this.setup.setMode(this.setup.mode);
    if (tab === "saved") void this.load();
  }

  async load() {
    byId("saved-error").hidden = true;
    try {
      this.games = (await api.savedGames()).games;
    } catch (error) {
      console.error(error);
      this.games = [];
      byId("saved-error").textContent = t("saved.loadError");
      byId("saved-error").hidden = false;
    }
    const known = new Set(this.games.map((game) => game.game_id));
    this.selected = new Set([...this.selected].filter((id) => known.has(id)));
    this.render();
  }

  /** @param {string} text */
  async importText(text) {
    this.startImport("import");
    let report;
    try {
      report = await api.importGames(text);
    } catch (error) {
      console.error(error);
      byId("import-summary").textContent = t("import.failed");
      return;
    }
    await this.showImport(report, "import");
    if (report.errors.length === 0 && report.imported > 0) byId("import-text").value = "";
  }

  /** Fetches a player's games from Lichess or Chess.com and imports them. */
  async importRemote() {
    const button = byId("import-fetch");
    const site = /** @type {"lichess" | "chesscom"} */ (byId("import-site").value);
    const username = byId("import-username").value.trim();
    this.startImport("import-remote");
    byId("import-remote-summary").textContent = t("import.remote.busy");
    button.disabled = true;
    try {
      const report = await api.importRemote(site, username, Number(byId("import-months").value));
      await this.showImport(report, "import-remote");
    } catch (error) {
      console.error(error);
      const code = error instanceof ApiError ? error.code : undefined;
      byId("import-remote-summary").textContent = code
        ? t(`import.remote.error.${code}`)
        : t("import.failed");
    } finally {
      button.disabled = false;
    }
  }

  /** @param {"import" | "import-remote"} prefix Which form's summary and error list. */
  startImport(prefix) {
    byId(`${prefix}-errors`).replaceChildren();
    byId(`${prefix}-summary`).hidden = false;
  }

  /**
   * @param {{imported: number, duplicates: number, updated?: number, errors: any[],
   *   fetched?: number, truncated?: boolean}} report
   * @param {"import" | "import-remote"} prefix
   */
  async showImport(report, prefix) {
    const summary = byId(`${prefix}-summary`);
    const errors = byId(`${prefix}-errors`);
    const total =
      report.imported + report.duplicates + (report.updated ?? 0) + report.errors.length;
    summary.textContent = total === 0
      ? t(report.fetched === undefined ? "import.nothing" : "import.remote.nothing")
      : t("import.summary", {
          imported: report.imported,
          duplicates: report.duplicates,
          failed: report.errors.length,
        });
    if (report.updated) {
      summary.textContent += ` ${t("import.updated", { updated: report.updated })}`;
    }
    if (report.truncated) {
      summary.textContent += ` ${t("import.remote.truncated", { max: report.fetched ?? 0 })}`;
    }
    errors.append(
      ...report.errors.map((/** @type {any} */ item) => {
        const line = document.createElement("li");
        line.textContent = t("import.errorLine", {
          index: item.index,
          label: item.label,
          reason: t(`import.error.${item.code}`),
        });
        return line;
      }),
    );
    await this.load();
  }

  visibleGames() {
    const query = byId("saved-search").value.trim().toLowerCase();
    const color = byId("saved-color").value;
    const result = byId("saved-result").value;
    return this.games.filter(
      (game) =>
        (!color || game.user_color === color) &&
        (!result || game.result === result) &&
        (!query || `${game.eco ?? ""} ${game.opening ?? ""}`.toLowerCase().includes(query)),
    );
  }

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

  /** Deleting needs a second click, like resigning; it cannot be undone. */
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

  resetDelete() {
    clearTimeout(this.deleteTimer);
    const button = byId("saved-delete");
    button.classList.remove("confirming");
    button.disabled = this.selected.size === 0;
    button.textContent = t("saved.delete", { count: this.selected.size });
  }

  async deleteSelected() {
    byId("saved-error").hidden = true;
    try {
      await api.deleteGames([...this.selected]);
      this.selected.clear();
    } catch (error) {
      console.error(error);
      byId("saved-error").textContent = t("saved.deleteError");
      byId("saved-error").hidden = false;
    }
    await this.load();
  }

  /** @param {SavedGame} game */
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
    name.textContent = `${eco}${game.opening ?? t("saved.noOpening")}`;
    const details = document.createElement("span");
    details.className = "variant-moves";
    const imported = game.source === "imported";
    details.textContent = (
      imported
        ? [
            t("saved.imported"),
            new Date(game.started_at).toLocaleDateString(undefined, { timeZone: "UTC" }),
            `${game.white} - ${game.black}`,
            t("saved.plies", { count: game.plies }),
          ]
        : [
            new Date(game.started_at).toLocaleString(),
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
      byId("saved-error").textContent = t("saved.exportError");
      byId("saved-error").hidden = false;
    }
  }
}
