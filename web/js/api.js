// Thin client for the backend API. Every call returns the parsed JSON body, or throws ApiError.

/** A request the server answered with an error status. */
export class ApiError extends Error {
  /**
   * Creates the error.
   * @param {number} status  The HTTP status.
   * @param {string} message  What failed, for the console.
   * @param {string} [code] The server's `detail`, when it is a string.
   */
  constructor(status, message, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

/**
 * Calls the API: GET without a body, POST with a JSON body.
 * @param {string} path  The path under `api`, such as `/games`.
 * @param {object} [body]  The JSON body, for a POST.
 * @returns {Promise<any>} The parsed response body.
 * @throws {ApiError} The server answered with an error status.
 */
async function request(path, body) {
  const options = body === undefined
    ? {}
    : {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      };
  const response = await fetch(`api${path}`, options);
  if (!response.ok) {
    const detail = await response.json().then((data) => data?.detail, () => undefined);
    const code = typeof detail === "string" ? detail : undefined;
    throw new ApiError(response.status, `${response.status} on ${path}`, code);
  }
  return response.json();
}

/** The API's endpoints. */
export const api = {
  /** @returns {Promise<any>} App version and engine. */
  health: () => request("/health"),
  /** @returns {Promise<any>} The book: families and their lines. */
  repertoires: () => request("/repertoires"),
  /** @returns {Promise<any>} The bot's levels and the default one. */
  levels: () => request("/engine/levels"),
  /** @returns {Promise<any>} The clock presets by category. */
  timeControls: () => request("/time-controls"),
  /** @returns {Promise<any>} The unfinished game, if any. */
  activeGame: () => request("/games/active"),
  /** @returns {Promise<any>} The finished games, newest first. */
  savedGames: () => request("/games"),
  /**
   * A saved game for the review.
   * @param {string} gameId  The game's id.
   * @returns {Promise<any>} Its moves and annotations.
   */
  reviewGame: (gameId) => request(`/games/${gameId}/review`),
  /**
   * A book line for the review.
   * @param {string} variantId  The line id.
   * @returns {Promise<any>} Its moves.
   */
  reviewLine: (variantId) => request(`/lines/${variantId}/review`),
  /**
   * Imports PGN text.
   * @param {string} pgn  One or more games.
   * @returns {Promise<any>} The import report.
   */
  importGames: (pgn) => request("/games/import", { pgn }),
  /**
   * Imports a player's public games from a site.
   * @param {"lichess" | "chesscom"} site  The site.
   * @param {string} username  The player's username.
   * @param {number} months  The period, this month included.
   * @returns {Promise<any>} The import report, with `fetched` and `truncated`.
   */
  importRemote: (site, username, months) =>
    request("/games/import/remote", { site, username, months }),
  /**
   * Deletes saved games for good.
   * @param {string[]} gameIds  The games.
   * @returns {Promise<any>} How many were deleted.
   */
  deleteGames: (gameIds) => request("/games/delete", { game_ids: gameIds }),
  /**
   * Saved games as one PGN file, oldest first.
   * @param {string[]} gameIds  The games.
   * @returns {Promise<Blob>} The PGN file.
   * @throws {ApiError} The server refused the export.
   */
  exportGames: async (gameIds) => {
    const response = await fetch("api/games/export", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ game_ids: gameIds }),
    });
    if (!response.ok) throw new ApiError(response.status, `${response.status} on export`);
    return response.blob();
  },
  /**
   * Book lines as one PGN file.
   * @param {string[]} variantIds  The lines.
   * @returns {Promise<Blob>} The PGN file.
   * @throws {ApiError} The server refused the export.
   */
  exportLines: async (variantIds) => {
    const response = await fetch("api/lines/export", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ variant_ids: variantIds }),
    });
    if (!response.ok) throw new ApiError(response.status, `${response.status} on export`);
    return response.blob();
  },
  /**
   * Starts a game.
   * @param {object} setup  The `POST /api/games` body.
   * @returns {Promise<any>} The game and the bot's first move, if it starts.
   */
  newGame: (setup) => request("/games", setup),
  /**
   * A Chess960 starting position.
   * @param {string} [fen]  A typed position; with no FEN, the server picks a random one.
   * @returns {Promise<{position: number, fen: string}>} The position.
   */
  chess960Start: (fen) => request("/chess960", { fen }),
  /**
   * Sends the user's move.
   * @param {string} gameId  The game's id.
   * @param {object} move  The move and the clocks.
   * @returns {Promise<any>} The user's move, the bot's reply and the state.
   */
  move: (gameId, move) => request(`/games/${gameId}/moves`, move),
  /**
   * Stockfish's evaluation of the position on screen.
   * @param {string} fen  The position.
   * @param {boolean} chess960  Whether it is a Chess960 game.
   * @returns {Promise<{cp: number | null, mate: number | null, best: string | null}>} From
   *   White's side.
   */
  evaluate: (fen, chess960) => request("/evaluate", { fen, chess960 }),
  /**
   * Resigns a game.
   * @param {string} gameId  The game's id.
   * @returns {Promise<any>} The finished game.
   */
  resign: (gameId) => request(`/games/${gameId}/resign`, {}),
  /**
   * Takes back the user's last move.
   * @param {string} gameId  The game's id.
   * @param {{shown_plies: number, user_clock_ms: number | null, bot_clock_ms: number | null}} body
   *   The plies shown and the clocks before the move.
   * @returns {Promise<any>} The state after it.
   */
  takeBack: (gameId, body) => request(`/games/${gameId}/takeback`, body),
  /**
   * Ends a game on time.
   * @param {string} gameId  The game's id.
   * @param {"user" | "bot"} side  Whose clock ran out.
   * @param {number} shownPlies  The plies on screen.
   * @returns {Promise<any>} The finished game.
   */
  timeout: (gameId, side, shownPlies) =>
    request(`/games/${gameId}/timeout`, { side, shown_plies: shownPlies }),
  /**
   * A game with its end-of-game report.
   * @param {string} gameId  The game's id.
   * @returns {Promise<any>} The game.
   */
  summary: (gameId) => request(`/games/${gameId}`),
};
