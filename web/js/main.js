// Wires the page together.

import { api } from "./api.js";
import { Board } from "./board.js";
import { GameController } from "./game.js";
import { indexOpenings } from "./opening-names.js";
import { OpeningsScreen } from "./openings.js";
import { availableLocales, getLocale, initI18n, localize, onLocaleChange, setLocale, t } from "./i18n.js";
import { initLayout } from "./layout.js";
import { getPref, setPref } from "./prefs.js";
import { Review } from "./review.js";
import { SavedGames } from "./saved.js";
import { SetupCard } from "./setup.js";
import { initSoundControls } from "./sound.js";
import { initTheme } from "./theme.js";
import { initTooltips } from "./tooltips.js";

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/** Lists the languages that have a UI file; each is named in its own language. */
async function initLocalePicker() {
  const select = byId("locale-picker");
  const locales = await availableLocales().catch(() => []);
  if (!locales.some((item) => item.code === getLocale())) {
    locales.unshift({ code: getLocale(), name: t("locale.name") });
  }
  for (const { code, name } of locales) select.add(new Option(name, code));
  select.value = getLocale();
  select.addEventListener("change", () => {
    setPref("locale", select.value);
    void setLocale(select.value);
  });
}

async function main() {
  await initI18n(getPref("locale", "en"));
  initTooltips();
  void initLocalePicker();
  initTheme(byId("theme-toggle"));
  initLayout();
  initSoundControls(byId("sound-toggle"), byId("sound-volume"));

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
  );
  game = new GameController(board);
  /** @type {Review | null} */
  let review = null;
  // The board's surroundings belong to the review while one is open, else to the game.
  onLocaleChange(() => (review?.active ? review.relocalize() : game.relocalize()));

  try {
    const [{ repertoires }, { levels, default: defaultLevel }, timeControls, health] = await Promise.all([
      api.repertoires(),
      api.levels(),
      api.timeControls(),
      api.health(),
    ]);
    indexOpenings(repertoires);
    const setup = new SetupCard(
      repertoires,
      levels,
      defaultLevel,
      timeControls,
      (color) => game.renderIdle(color, setup.previewFen()),
      (chosen) => {
        review?.close();
        void game.start(chosen);
      },
    );
    new OpeningsScreen(repertoires, (variantId) => void review?.openLine(variantId));
    review = new Review(
      board,
      () => game.renderIdle(setup.color, setup.previewFen()),
      (gameId, ply) => {
        byId("tab-new").click();
        void setup.chooseSaved(gameId, ply);
      },
    );
    game.renderIdle(setup.color);
    new SavedGames(
      (key) => setup.timeLabelFor(key),
      setup,
      (gameId) => void review?.openGame(gameId),
      () => {
        review?.close();
        game.leaveGame();
      },
    );
    game.previewFen = () => setup.previewFen();
    const { game: active } = await api.activeGame();
    if (active) game.resume(active, setup.clockFor(active.setup.time_control));
    const buildTag = health.engine.build_tag ? ` (${health.engine.build_tag})` : "";
    byId("footer-versions").textContent =
      `Chess Trainer ${health.app_version} · ${health.engine.name}${buildTag}`;
  } catch (error) {
    console.error(error);
    localize(byId("setup-hint"), () => {
      byId("setup-hint").textContent = t("setup.loadError");
    });
    byId("setup-hint").hidden = false;
    byId("play").disabled = true;
  }
}

void main();
