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
  /** @param {object} setup */
  newGame: (setup) => request("/games", setup),
  /**
   * @param {string} gameId
   * @param {object} move
   */
  move: (gameId, move) => request(`/games/${gameId}/moves`, move),
  /** @param {string} gameId */
  resign: (gameId) => request(`/games/${gameId}/resign`, {}),
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
