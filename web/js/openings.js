// The Openings screen: like Saved Games, it views lines on the board and exports them as PGN.

import { api } from "./api.js";
import { saveFile } from "./download.js";
import { localize, onLocaleChange, t } from "./i18n.js";
import { OpeningTree } from "./opening-tree.js";

/**
 * Finds an element by id.
 * @param {string} id  The element's id.
 * @returns {any} The element.
 */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/** The Openings screen: searches the book's lines, views one, exports the ticked ones. */
export class OpeningsScreen {
  /**
   * Builds the screen's tree of lines.
   * @param {import("./setup.js").RepertoireInfo[]} repertoires  The book.
   * @param {(variantId: string) => void} onView  Opens a line on the board.
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

  /** Labels and enables the export button with the number of ticked lines. */
  renderExport() {
    const count = this.tree.selected.size;
    byId("lines-export").disabled = count === 0;
    byId("lines-export").textContent = t("lines.export", { count });
  }

  /**
   * Downloads the ticked lines as one PGN file, or shows an error.
   * @returns {Promise<void>}
   */
  async exportSelected() {
    byId("lines-error").hidden = true;
    try {
      const blob = await api.exportLines([...this.tree.selected]);
      const date = new Date().toISOString().slice(0, 10);
      saveFile(blob, `chess-trainer-lines-${date}.pgn`);
    } catch (error) {
      console.error(error);
      localize(byId("lines-error"), () => {
        byId("lines-error").textContent = t("lines.exportError");
      });
      byId("lines-error").hidden = false;
    }
  }
}
