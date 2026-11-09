// UI strings. Adding a language is one JSON file in web/i18n (brief §8).
// The language can change at any moment, mid-game included: everything on screen is drawn again
// without reloading the page.

const DEFAULT_LOCALE = "en";

/** @type {Record<string, string>} English, the fallback for any key a language lacks. */
let fallback = {};
/** @type {Record<string, string>} */
let strings = {};
let locale = DEFAULT_LOCALE;
// Bumped on every switch, so a slow file that arrives after a newer choice is ignored.
let loading = 0;

/** @type {Set<() => void>} */
const listeners = new Set();
/** @type {Map<Element, () => void>} */
const bound = new Map();

/** @param {string} name */
async function fetchStrings(name) {
  const response = await fetch(`i18n/${encodeURIComponent(name)}.json`);
  if (!response.ok) throw new Error(`cannot load strings for ${name}`);
  return /** @type {Promise<Record<string, string>>} */ (response.json());
}

/**
 * Loads a language, falling back to English when its file is missing.
 * @param {string} requested
 * @returns {Promise<boolean>} False when a newer switch started meanwhile.
 */
async function load(requested) {
  const ticket = ++loading;
  if (Object.keys(fallback).length === 0) fallback = await fetchStrings(DEFAULT_LOCALE);
  let chosen = requested;
  let own = fallback;
  if (requested !== DEFAULT_LOCALE) {
    try {
      own = await fetchStrings(requested);
    } catch (error) {
      console.error(error);
      chosen = DEFAULT_LOCALE;
    }
  }
  if (ticket !== loading) return false;
  strings = { ...fallback, ...own };
  locale = chosen;
  document.documentElement.lang = locale;
  return true;
}

/** @param {string} requested */
export async function initI18n(requested = DEFAULT_LOCALE) {
  await load(requested);
  applyI18n(document);
}

/**
 * Switches the language and draws again everything on screen.
 * @param {string} requested
 */
export async function setLocale(requested) {
  if (!(await load(requested))) return;
  applyI18n(document);
  for (const [element, render] of bound) {
    if (element.isConnected) render();
    else bound.delete(element);
  }
  for (const listener of listeners) listener();
}

export function getLocale() {
  return locale;
}

/**
 * Called after every language switch, to draw again what a module rendered with `t()`.
 * @param {() => void} listener
 */
export function onLocaleChange(listener) {
  listeners.add(listener);
}

/**
 * Renders an element now and again after every language switch, while it is in the page.
 * An element bound here must always be written through here, or a switch brings back old text.
 * @param {Element} element
 * @param {() => void} render
 */
export function localize(element, render) {
  bound.set(element, render);
  render();
}

/**
 * The languages that have a file in web/i18n, each named in its own language.
 * @returns {Promise<{code: string, name: string}[]>}
 */
export async function availableLocales() {
  const response = await fetch("api/locales");
  if (!response.ok) return [{ code: DEFAULT_LOCALE, name: t("locale.name") }];
  return (await response.json()).locales;
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
    element.textContent = t(element.getAttribute("data-i18n") ?? "");
  }
  for (const element of root.querySelectorAll("[data-i18n-placeholder]")) {
    element.setAttribute("placeholder", t(element.getAttribute("data-i18n-placeholder") ?? ""));
  }
  for (const element of root.querySelectorAll("[data-i18n-label]")) {
    element.setAttribute("aria-label", t(element.getAttribute("data-i18n-label") ?? ""));
  }
}

/**
 * Picks a name from the `names` table shape, falling back to English.
 * @param {Record<string, string>} names
 */
export function localizedName(names) {
  return names[locale] ?? names[DEFAULT_LOCALE] ?? "";
}
