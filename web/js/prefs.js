// UI preferences, kept per browser in localStorage (brief §8): they are not saved on the server.
// Storage can be unavailable (private window, blocked site data), so every access is guarded.

const KEY = "chess-trainer.prefs";

/**
 * Reads every stored preference.
 * @returns {Record<string, unknown>} The preferences, or none if storage fails.
 */
function readAll() {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") ?? {};
  } catch {
    return {};
  }
}

/**
 * Reads a preference.
 * @template T
 * @param {string} name  The preference's name.
 * @param {T} fallback  What to use when it is not stored.
 * @returns {T} The stored value, or the fallback.
 */
export function getPref(name, fallback) {
  return readAll()[name] ?? fallback;
}

/**
 * Stores a preference; does nothing if storage fails.
 * @param {string} name  The preference's name.
 * @param {unknown} value  The value, stored as JSON.
 */
export function setPref(name, value) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...readAll(), [name]: value }));
  } catch {
    // Preferences are a convenience: the app works without them.
  }
}
