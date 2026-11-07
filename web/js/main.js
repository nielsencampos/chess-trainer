// Wires the page together.

import { api } from "./api.js";
import { Board, PIECE_SETS } from "./board.js";
import { GameController } from "./game.js";
import { initI18n, t } from "./i18n.js";
import { initLayout } from "./layout.js";
import { getPref, setPref } from "./prefs.js";
import { Review } from "./review.js";
import { SavedGames } from "./saved.js";
import { SetupCard } from "./setup.js";
import { initSoundControls } from "./sound.js";
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
  initLayout();
  initSoundControls(byId("sound-toggle"), byId("sound-volume"), t);

  const savedSet = getPref("pieceSet", "cburnett");
  const pieceSet = PIECE_SETS.includes(savedSet) ? savedSet : "cburnett";
  /** @type {GameController} */
  let game;
  const board = new Board(
    byId("board"),
    {
      legalMoves: (square) => game.legalMoves(square),
      onMove: (from, to, promotion) => void game.onUserMove(from, to, promotion),
      premoveTargets: (square) => game.premoveTargets(square),
      onPremove: (from, to) => game.setPremove(from, to),
      onPremoveCancel: () => game.clearPremove(),
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
      (chosen) => {
        review.close();
        void game.start(chosen);
      },
      (variantId) => void review.openLine(variantId),
    );
    const review = new Review(
      board,
      () => game.renderIdle(setup.color),
      (gameId, ply) => {
        byId("tab-from-saved").click();
        void setup.chooseSaved(gameId, ply);
      },
    );
    game.renderIdle(setup.color);
    new SavedGames(
      (key) => setup.timeLabelFor(key),
      setup,
      (gameId) => void review.openGame(gameId),
    );
    const { game: active } = await api.activeGame();
    if (active) game.resume(active, setup.clockFor(active.setup.time_control));
    const buildTag = health.engine.build_tag ? ` (${health.engine.build_tag})` : "";
    byId("footer-versions").textContent =
      `Chess Trainer ${health.app_version} · ${health.engine.name}${buildTag}`;
  } catch (error) {
    console.error(error);
    byId("setup-hint").textContent = t("setup.loadError");
    byId("setup-hint").hidden = false;
    byId("play").disabled = true;
  }
}

void main();
