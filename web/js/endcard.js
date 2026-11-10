// End-of-game card, under the move list: result, variation, how far theory went, deviations, PGN.

import { saveFile } from "./download.js";
import { localizedName, t } from "./i18n.js";
import { moveIcon } from "./icons.js";
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
 */
function downloadPgn(pgn) {
  const date = new Date().toISOString().slice(0, 10);
  saveFile(new Blob([pgn], { type: "application/x-chess-pgn" }), `chess-trainer-${date}.pgn`);
}

/**
 * A move's number as a scoresheet writes it.
 * @param {number} ply  The move's ply.
 * @param {string} san  The move.
 * @returns {{number: string, san: string}} `12.` for White, `12...` for Black, and the move.
 */
function numbered(ply, san) {
  const number = Math.ceil(ply / 2);
  return { number: ply % 2 === 1 ? `${number}.` : `${number}...`, san };
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
    const { number, san } = numbered(deviation.ply, deviation.played_san);
    const item = document.createElement("li");
    const played = document.createElement("span");
    played.className = "played";
    played.textContent = `${number} ${san}`;
    item.append(moveIcon("deviation", t("icon.deviation")), played, ` — ${t("end.deviationLine", { expected: deviation.expected_san.join(", ") })}`);
    list.append(item);
  }
  const bot = summary.state.bot_deviation;
  if (bot) {
    const { number, san } = numbered(bot.ply, bot.played_san);
    const item = document.createElement("li");
    const played = document.createElement("span");
    played.className = "played";
    played.textContent = `${number} ${san}`;
    item.append(moveIcon("deviation", t("icon.botDeviation")), played, ` — ${t("end.botDeviationLine", { expected: bot.expected_san.join(", ") })}`);
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
