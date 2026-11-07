// The "Saved games" tab: finished games, filters, selection and export.

import { api } from "./api.js";
import { t } from "./i18n.js";

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/**
 * @typedef {{game_id: string, started_at: string, user_color: string, time_control: string,
 *   level: string, result: string, termination: string, eco: string | null,
 *   opening: string | null, plies: number, source: string,
 *   white: string | null, black: string | null}} SavedGame
 */

export class SavedGames {
  /** @param {(key: string) => string} timeLabel */
  constructor(timeLabel) {
    this.timeLabel = timeLabel;
    /** @type {SavedGame[]} */
    this.games = [];
    /** @type {Set<string>} */
    this.selected = new Set();

    byId("tab-new").addEventListener("click", () => this.showTab("new"));
    byId("tab-saved").addEventListener("click", () => this.showTab("saved"));
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
    byId("import-paste").addEventListener("click", () => {
      void this.importText(byId("import-text").value);
    });
    byId("import-file").addEventListener("change", async (/** @type {any} */ event) => {
      const [file] = event.target.files;
      event.target.value = ""; // So the same file can be chosen again.
      if (file) await this.importText(await file.text());
    });
  }

  /** @param {"new" | "saved"} tab */
  showTab(tab) {
    byId("setup-card").hidden = tab !== "new";
    byId("saved-card").hidden = tab !== "saved";
    byId("tab-new").classList.toggle("active", tab === "new");
    byId("tab-saved").classList.toggle("active", tab === "saved");
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
    const summary = byId("import-summary");
    const errors = byId("import-errors");
    errors.replaceChildren();
    summary.hidden = false;
    let report;
    try {
      report = await api.importGames(text);
    } catch (error) {
      console.error(error);
      summary.textContent = t("import.failed");
      return;
    }
    const total = report.imported + report.duplicates + report.errors.length;
    summary.textContent = total === 0
      ? t("import.nothing")
      : t("import.summary", {
          imported: report.imported,
          duplicates: report.duplicates,
          failed: report.errors.length,
        });
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
    if (report.errors.length === 0 && report.imported > 0) byId("import-text").value = "";
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
    label.append(box, text, result);
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
