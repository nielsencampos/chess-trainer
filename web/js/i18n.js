// UI strings. Adding a language is one JSON file in web/i18n (brief §8).
// The language can change at any moment, mid-game included: everything on screen is drawn again
// without reloading the page.

/** The fallback language, English (US). */
export const DEFAULT_LOCALE = "en-US";
/** Codes used before the region was part of them, as a browser may still have them saved. */
const RENAMED = /** @type {Record<string, string>} */ ({ en: "en-US", es: "es-419" });

/** @type {Record<string, string>} English, the fallback for any key a language lacks. */
let fallback = {};
/** @type {Record<string, string>} */
let strings = {};
/** @type {Record<string, string>} The current language's own strings, without the fallback. */
let own = {};
let locale = DEFAULT_LOCALE;
// Bumped on every switch, so a slow file that arrives after a newer choice is ignored.
let loading = 0;
/** @type {Promise<{code: string, name: string, dir: string}[]> | null} The registry's list, once. */
let localeList = null;

/** @type {Set<() => void>} */
const listeners = new Set();
/** @type {Map<Element, () => void>} */
const bound = new Map();

/**
 * Downloads one language's UI strings.
 * @param {string} name  The language code.
 * @returns {Promise<Record<string, string>>} Key -> string.
 * @throws {Error} The file cannot be loaded.
 */
async function fetchStrings(name) {
  const response = await fetch(`i18n/${encodeURIComponent(name)}.json`);
  if (!response.ok) throw new Error(`cannot load strings for ${name}`);
  return /** @type {Promise<Record<string, string>>} */ (response.json());
}

/**
 * Loads a language, falling back to English when its file is missing.
 * @param {string} requested  The language code.
 * @returns {Promise<boolean>} False when a newer switch started meanwhile.
 */
async function load(requested) {
  const ticket = ++loading;
  if (Object.keys(fallback).length === 0) fallback = await fetchStrings(DEFAULT_LOCALE);
  let chosen = requested;
  let mine = fallback;
  if (requested !== DEFAULT_LOCALE) {
    try {
      mine = await fetchStrings(requested);
    } catch (error) {
      console.error(error);
      chosen = DEFAULT_LOCALE;
    }
  }
  const direction = await localeDirection(chosen);
  if (ticket !== loading) return false;
  own = mine;
  strings = { ...fallback, ...own };
  locale = chosen;
  document.documentElement.lang = locale;
  document.documentElement.dir = direction;
  return true;
}

/**
 * A language's text direction, from the locale registry through `/api/locales` (brief §8).
 * @param {string} code  The language code.
 * @returns {Promise<string>} `rtl` or `ltr`; `ltr` when the list cannot be loaded.
 */
async function localeDirection(code) {
  const locales = await availableLocales().catch(() => []);
  return locales.find((item) => item.code === code)?.dir === "rtl" ? "rtl" : "ltr";
}

/**
 * Loads the first language and translates the page.
 * @param {string} [requested]  The language code; English by default.
 * @returns {Promise<void>}
 */
export async function initI18n(requested = DEFAULT_LOCALE) {
  await load(RENAMED[requested] ?? requested);
  applyI18n(document);
}

/**
 * Switches the language and draws again everything on screen.
 * @param {string} requested  The language code.
 * @returns {Promise<void>}
 */
export async function setLocale(requested) {
  if (!(await load(requested))) return;
  refresh();
}

/**
 * Draws again everything on screen in the current language, as after a switch. The move
 * notation (notation.js) uses it too.
 * @returns {void}
 */
export function refresh() {
  applyI18n(document);
  for (const [element, render] of bound) {
    if (element.isConnected) render();
    else bound.delete(element);
  }
  for (const listener of listeners) listener();
}

/**
 * The language in use.
 * @returns {string} Its code, such as `pt-BR`.
 */
export function getLocale() {
  return locale;
}

/**
 * The language in use, for formatting dates and numbers: always with Western digits (0-9), which
 * the move numbers, clocks and board coordinates use too, also in Arabic and Persian (#37).
 * @returns {string} Its code with the Latin numbering system, such as `ar-u-nu-latn`.
 */
export function getFormatLocale() {
  return `${locale}-u-nu-latn`;
}

/**
 * Called after every language switch, to draw again what a module rendered with `t()`.
 * @param {() => void} listener  Draws the module's text again.
 * @returns {void}
 */
export function onLocaleChange(listener) {
  listeners.add(listener);
}

/**
 * Renders an element now and again after every language switch, while it is in the page.
 * An element bound here must always be written through here, or a switch brings back old text.
 * @param {Element} element  The element.
 * @param {() => void} render  Writes its text.
 * @returns {void}
 */
export function localize(element, render) {
  bound.set(element, render);
  render();
}

/**
 * The languages that have a file in web/i18n, each named in its own language with its text
 * direction. Asked once; a failed request is asked again next time.
 * @returns {Promise<{code: string, name: string, dir: string}[]>} The languages, English first.
 */
export async function availableLocales() {
  localeList ??= fetch("api/locales").then(async (response) => {
    if (!response.ok) throw new Error("cannot load the list of languages");
    return (await response.json()).locales;
  });
  try {
    return [...(await localeList)];
  } catch (error) {
    localeList = null;
    throw error;
  }
}

/**
 * A UI string in the current language, with its `{placeholders}` filled.
 * With a numeric `count`, the key's plural form for that number is used.
 * @param {string} key  The string's key, such as `setup.play`.
 * @param {Record<string, string | number>} [params]  Values for the placeholders.
 * @returns {string} The string, or the key itself if no language has it.
 */
export function t(key, params = {}) {
  const template = strings[pluralKey(key, params.count)] ?? strings[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? `{${name}}`));
}

/**
 * A UI string with some placeholders filled by page elements, such as moves drawn in the chosen
 * notation, which plain text cannot hold.
 * @param {string} key  The string's key.
 * @param {Record<string, string | number | Node>} params  Values for the placeholders.
 * @returns {DocumentFragment} The string, as text and those elements.
 */
export function tNodes(key, params) {
  /** @type {Node[]} */
  const nodes = [];
  /** @type {Record<string, string | number>} */
  const texts = {};
  for (const [name, value] of Object.entries(params)) {
    if (value instanceof Node) {
      texts[name] = `\u0001${nodes.length}\u0001`;
      nodes.push(value);
    } else {
      texts[name] = value;
    }
  }
  const fragment = document.createDocumentFragment();
  t(key, texts)
    .split("\u0001")
    .forEach((part, index) => {
      if (index % 2 === 1) fragment.append(nodes[Number(part)]);
      else if (part) fragment.append(part);
    });
  return fragment;
}

/**
 * The key of a string's plural form for a number.
 * A key with a number has one entry per plural form of the locale: `saved.count.one`,
 * `saved.count.other` (and `few`, `many`… where the language has them).
 * @param {string} key  The base key.
 * @param {string | number | undefined} count  The number, if any.
 * @returns {string} The plural key, `.other` if the form is missing, or the key without a number.
 */
function pluralKey(key, count) {
  if (typeof count !== "number") return key;
  const form = new Intl.PluralRules(locale).select(count);
  return `${key}.${form}` in strings ? `${key}.${form}` : `${key}.other`;
}

/**
 * Translates the `data-i18n*` attributes of an element and everything inside it.
 * @param {Document | Element} root  Where to translate.
 * @returns {void}
 */
function applyI18n(root) {
  for (const element of root.querySelectorAll("[data-i18n]")) {
    const key = element.getAttribute("data-i18n") ?? "";
    element.textContent = t(key);
    // English shown in another language keeps English rules: with lang="tr", uppercase would
    // turn its "i" into "İ". A variant of English (en-GB) holds only what differs, on purpose.
    if (key in own || !(key in fallback) || locale.startsWith("en-")) element.removeAttribute("lang");
    else element.setAttribute("lang", DEFAULT_LOCALE);
  }
  for (const element of root.querySelectorAll("[data-i18n-placeholder]")) {
    element.setAttribute("placeholder", t(element.getAttribute("data-i18n-placeholder") ?? ""));
  }
  for (const element of root.querySelectorAll("[data-i18n-label]")) {
    element.setAttribute("aria-label", t(element.getAttribute("data-i18n-label") ?? ""));
  }
  // Icon-only buttons: the text is both the accessible name and the tooltip.
  for (const element of root.querySelectorAll("[data-i18n-title]")) {
    const text = t(element.getAttribute("data-i18n-title") ?? "");
    element.setAttribute("aria-label", text);
    element.setAttribute("title", text);
  }
}

/**
 * Picks a name from the `names` table shape, falling back to English.
 * @param {Record<string, string>} names  Locale -> name.
 * @returns {string} The name, or an empty string.
 */
export function localizedName(names) {
  return names[locale] ?? names[DEFAULT_LOCALE] ?? "";
}
