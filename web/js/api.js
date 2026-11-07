// Thin client for the backend API.

export class ApiError extends Error {
  /**
   * @param {number} status
   * @param {string} message
   */
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/**
 * @param {string} path
 * @param {object} [body]
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
    throw new ApiError(response.status, `${response.status} on ${path}`);
  }
  return response.json();
}

export const api = {
  health: () => request("/health"),
  repertoires: () => request("/repertoires"),
  levels: () => request("/engine/levels"),
  timeControls: () => request("/time-controls"),
  activeGame: () => request("/games/active"),
  savedGames: () => request("/games"),
  /** @param {string} gameId */
  reviewGame: (gameId) => request(`/games/${gameId}/review`),
  /** @param {string} variantId */
  reviewLine: (variantId) => request(`/lines/${variantId}/review`),
  /** @param {string} pgn */
  importGames: (pgn) => request("/games/import", { pgn }),
  /** @param {string[]} gameIds */
  exportGames: async (gameIds) => {
    const response = await fetch("api/games/export", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ game_ids: gameIds }),
    });
    if (!response.ok) throw new ApiError(response.status, `${response.status} on export`);
    return response.blob();
  },
  /** @param {string[]} variantIds */
  exportLines: async (variantIds) => {
    const response = await fetch("api/lines/export", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ variant_ids: variantIds }),
    });
    if (!response.ok) throw new ApiError(response.status, `${response.status} on export`);
    return response.blob();
  },
  /** @param {object} setup */
  newGame: (setup) => request("/games", setup),
  /** @param {string} [fen]  With no FEN, the server picks a random position. */
  chess960Start: (fen) => request("/chess960", { fen }),
  /**
   * @param {string} gameId
   * @param {object} move
   */
  move: (gameId, move) => request(`/games/${gameId}/moves`, move),
  /** @param {string} gameId */
  /**
   * @param {string} fen
   * @param {boolean} chess960
   * @returns {Promise<{cp: number | null, mate: number | null, best: string | null}>}
   */
  evaluate: (fen, chess960) => request("/evaluate", { fen, chess960 }),
  resign: (gameId) => request(`/games/${gameId}/resign`, {}),
  /**
   * @param {string} gameId
   * @param {{shown_plies: number, user_clock_ms: number | null, bot_clock_ms: number | null}} body
   */
  takeBack: (gameId, body) => request(`/games/${gameId}/takeback`, body),
  /**
   * @param {string} gameId
   * @param {"user" | "bot"} side
   * @param {number} shownPlies
   */
  timeout: (gameId, side, shownPlies) =>
    request(`/games/${gameId}/timeout`, { side, shown_plies: shownPlies }),
  /** @param {string} gameId */
  summary: (gameId) => request(`/games/${gameId}`),
};
