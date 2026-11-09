// The Openings screen: like Saved Games, it views lines on the board and exports them as PGN.

import { api } from "./api.js";
import { localize, onLocaleChange, t } from "./i18n.js";
import { OpeningTree } from "./opening-tree.js";

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

export class OpeningsScreen {
  /**
   * @param {import("./setup.js").RepertoireInfo[]} repertoires
   * @param {(variantId: string) => void} onView
   */
  constructor(repertoires, onView) {
    this.tree = new OpeningTree(
      repertoires,
      {
        search: byId("lines-search"),
        container: byId("lines-tree"),
        total: byId("lines-total"),
        selectAll: byId("lines-select-all"),
        clear: byId("lines-clear"),
        noMatches: byId("lines-no-matches"),
      },
      [],
      () => this.renderExport(),
      onView,
    );
    byId("lines-export").addEventListener("click", () => void this.exportSelected());
    this.renderExport();
    onLocaleChange(() => {
      this.tree.relocalize();
      this.renderExport();
    });
  }

  renderExport() {
    const count = this.tree.selected.size;
    byId("lines-export").disabled = count === 0;
    byId("lines-export").textContent = t("lines.export", { count });
  }

  async exportSelected() {
    byId("lines-error").hidden = true;
    try {
      const blob = await api.exportLines([...this.tree.selected]);
      const date = new Date().toISOString().slice(0, 10);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `chess-trainer-lines-${date}.pgn`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      console.error(error);
      localize(byId("lines-error"), () => {
        byId("lines-error").textContent = t("lines.exportError");
      });
      byId("lines-error").hidden = false;
    }
  }
}
