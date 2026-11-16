// End-of-game card, under the move list: result, variation, how far theory went, deviations, PGN.

import { saveFile } from "./download.js";
import { localizedName, t, tNodes } from "./i18n.js";
import { moveIcon } from "./icons.js";
import { sanElement } from "./notation.js";
import { openingName } from "./opening-names.js";

const COPY_FEEDBACK_MS = 1500;

/**
 * Finds an element by id.
 * @param {string} id  The element's id.
 * @returns {any} The element.
 */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/**
 * Copies text to the clipboard, also on plain http where the Clipboard API is missing.
 * @param {string} text  The text.
 * @returns {Promise<void>}
 * @throws {Error} The browser refused to copy.
 */
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // Fallback for plain http on a network address, where the Clipboard API does not exist.
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  if (!ok) throw new Error("copy failed");
}

/**
 * Downloads a PGN as a dated file.
 * @param {string} pgn  The PGN text.
 * @returns {void}
 */
function downloadPgn(pgn) {
  const date = new Date().toISOString().slice(0, 10);
  saveFile(new Blob([pgn], { type: "application/x-chess-pgn" }), `chess-trainer-${date}.pgn`);
}

/**
 * A move with its number as a scoresheet writes it, in the chosen notation.
 * @param {number} ply  The move's ply.
 * @param {string} san  The move, in English SAN.
 * @returns {HTMLSpanElement} `12. Nf3` for White, `12... Nf6` for Black.
 */
function numbered(ply, san) {
  const number = Math.ceil(ply / 2);
  const played = document.createElement("span");
  played.className = "played";
  // "12. Nf3" reads left to right in a right-to-left language too (#37).
  played.dir = "ltr";
  played.tabIndex = 0;
  played.dataset.tip = "";
  played.append(ply % 2 === 1 ? `${number}. ` : `${number}... `, sanElement(san));
  return played;
}

/**
 * Moves the line expected, in the chosen notation, separated by commas.
 * @param {string[]} sans  The moves, in English SAN.
 * @returns {DocumentFragment} The moves.
 */
function expectedMoves(sans) {
  const fragment = document.createDocumentFragment();
  sans.forEach((san, index) => {
    if (index > 0) fragment.append(", ");
    const move = document.createElement("span");
    move.className = "expected";
    move.tabIndex = 0;
    move.dataset.tip = "";
    move.append(sanElement(san));
    fragment.append(move);
  });
  return fragment;
}

/**
 * Fills the end-of-game card: result, variation, theory, deviations and the PGN buttons.
 * @param {any} summary  The API's GameSummary.
 * @returns {void}
 */
export function renderEndCard(summary) {
  byId("end-result").textContent = t(`end.${summary.result}`);
  byId("end-termination").textContent = t(`end.termination.${summary.termination}`);

  const eco = summary.eco ? `${summary.eco} · ` : "";
  byId("end-variation").textContent = `${eco}${summary.opening ? openingName(summary.opening) : localizedName(summary.variant_names)}`;

  const theoryPlies = summary.state.theory_until_ply;
  byId("end-theory").textContent = theoryPlies === 0
    ? t("end.theoryNone")
    : t("end.theoryUntil", {
        move: Math.ceil(theoryPlies / 2),
        plies: theoryPlies,
        total: summary.total_plies,
      });

  const list = byId("end-deviations");
  list.replaceChildren();
  if (summary.deviations.length === 0 && !summary.state.bot_deviation) {
    const item = document.createElement("li");
    item.className = "muted";
    item.textContent = t("end.noDeviations");
    list.append(item);
  }
  for (const deviation of summary.deviations) {
    const item = document.createElement("li");
    item.append(
      moveIcon("deviation", t("icon.deviation")),
      numbered(deviation.ply, deviation.played_san),
      " — ",
      tNodes("end.deviationLine", { expected: expectedMoves(deviation.expected_san) }),
    );
    list.append(item);
  }
  const bot = summary.state.bot_deviation;
  if (bot) {
    const item = document.createElement("li");
    item.append(
      moveIcon("deviation", t("icon.botDeviation")),
      numbered(bot.ply, bot.played_san),
      " — ",
      tNodes("end.botDeviationLine", { expected: expectedMoves(bot.expected_san) }),
    );
    list.append(item);
  }

  const copyButton = byId("copy-pgn");
  copyButton.hidden = false;
  copyButton.textContent = t("end.copyPgn");
  copyButton.onclick = async () => {
    try {
      await copyText(summary.pgn);
      copyButton.textContent = t("end.copied");
    } catch {
      copyButton.textContent = t("end.copyFailed");
    }
    setTimeout(() => {
      copyButton.textContent = t("end.copyPgn");
    }, COPY_FEEDBACK_MS);
  };

  const downloadButton = byId("download-pgn");
  downloadButton.hidden = false;
  downloadButton.onclick = () => downloadPgn(summary.pgn);
}
