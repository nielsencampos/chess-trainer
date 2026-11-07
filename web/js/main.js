// Wires the page together.

import { api } from "./api.js";
import { Board, PIECE_SETS } from "./board.js";
import { GameController } from "./game.js";
import { initI18n, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";
import { SetupCard } from "./setup.js";
import { initTheme } from "./theme.js";

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

function initPiecePicker(/** @type {Board} */ board) {
  const select = byId("piece-set");
  for (const key of PIECE_SETS) select.add(new Option(t(`board.pieceSet.${key}`), key));
  select.value = board.pieceSet;
  select.addEventListener("change", () => {
    setPref("pieceSet", select.value);
    board.setPieceSet(select.value);
  });
}

async function main() {
  await initI18n(getPref("locale", "en"));
  initTheme(byId("theme-toggle"));

  const savedSet = getPref("pieceSet", "cburnett");
  const pieceSet = PIECE_SETS.includes(savedSet) ? savedSet : "cburnett";
  /** @type {GameController} */
  let game;
  const board = new Board(
    byId("board"),
    {
      legalMoves: (square) => game.legalMoves(square),
      onMove: (from, to, promotion) => void game.onUserMove(from, to, promotion),
    },
    pieceSet,
  );
  game = new GameController(board);
  initPiecePicker(board);

  try {
    const [{ repertoires }, { levels, default: defaultLevel }, timeControls, health] = await Promise.all([
      api.repertoires(),
      api.levels(),
      api.timeControls(),
      api.health(),
    ]);
    const setup = new SetupCard(
      repertoires,
      levels,
      defaultLevel,
      timeControls,
      (color) => game.renderIdle(color),
      (chosen) => void game.start(chosen),
    );
    game.renderIdle(setup.color);
    const buildTag = health.engine.build_tag ? ` (${health.engine.build_tag})` : "";
    byId("footer-versions").textContent =
      `chess-trainer ${health.app_version} · ${health.engine.name}${buildTag}`;
  } catch (error) {
    console.error(error);
    byId("setup-hint").textContent = t("setup.loadError");
    byId("setup-hint").hidden = false;
    byId("play").disabled = true;
  }
}

void main();
