// UI preferences. Browser storage only until Phase 2 moves them to the server `settings` table.
// Storage can be unavailable (private window, blocked site data), so every access is guarded.

const KEY = "chess-trainer.prefs";

function readAll() {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") ?? {};
  } catch {
    return {};
  }
}

/**
 * @template T
 * @param {string} name
 * @param {T} fallback
 * @returns {T}
 */
export function getPref(name, fallback) {
  return readAll()[name] ?? fallback;
}

/**
 * @param {string} name
 * @param {unknown} value
 */
export function setPref(name, value) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...readAll(), [name]: value }));
  } catch {
    // Preferences are a convenience: the app works without them.
  }
}
