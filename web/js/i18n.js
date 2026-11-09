// UI strings. Adding a language is one JSON file in web/i18n (brief §8).

const DEFAULT_LOCALE = "en";

/** @type {Record<string, string>} */
let strings = {};
let locale = DEFAULT_LOCALE;

/** @param {string} requested */
export async function initI18n(requested = DEFAULT_LOCALE) {
  const response = await fetch(`i18n/${encodeURIComponent(requested)}.json`);
  if (!response.ok) {
    if (requested !== DEFAULT_LOCALE) return initI18n(DEFAULT_LOCALE);
    throw new Error(`cannot load strings for ${requested}`);
  }
  strings = await response.json();
  locale = requested;
  document.documentElement.lang = locale;
  applyI18n(document);
}

/**
 * @param {string} key
 * @param {Record<string, string | number>} [params]
 */
export function t(key, params = {}) {
  const template = strings[pluralKey(key, params.count)] ?? strings[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`));
}

/**
 * A key with a number has one entry per plural form of the locale: `saved.count.one`,
 * `saved.count.other` (and `few`, `many`… where the language has them).
 * @param {string} key
 * @param {string | number | undefined} count
 */
function pluralKey(key, count) {
  if (typeof count !== "number") return key;
  const form = new Intl.PluralRules(locale).select(count);
  return `${key}.${form}` in strings ? `${key}.${form}` : `${key}.other`;
}

/** @param {Document | Element} root */
export function applyI18n(root) {
  for (const element of root.querySelectorAll("[data-i18n]")) {
    element.textContent = t(element.getAttribute("data-i18n"));
  }
  for (const element of root.querySelectorAll("[data-i18n-placeholder]")) {
    element.setAttribute("placeholder", t(element.getAttribute("data-i18n-placeholder")));
  }
  for (const element of root.querySelectorAll("[data-i18n-label]")) {
    element.setAttribute("aria-label", t(element.getAttribute("data-i18n-label")));
  }
}

/**
 * Picks a name from the `names` table shape, falling back to English.
 * @param {Record<string, string>} names
 */
export function localizedName(names) {
  return names[locale] ?? names[DEFAULT_LOCALE] ?? "";
}
