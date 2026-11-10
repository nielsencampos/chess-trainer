// Opening names in the chosen language. The server names positions with the Lichess catalog,
// in English. Every catalog name is the `opening` of some book line, and it reads as the family's
// name, a separator and the line's name ("Sicilian Defense" + ": " + "Najdorf Variation", or
// "Queen's Gambit" + " " + "Declined: Orthodox Defense"), so it is translated from their names.

import { getLocale } from "./i18n.js";

/**
 * @typedef {{family: Record<string, string>, line: Record<string, string>}} NameParts
 */

/** @type {Map<string, NameParts>} English catalog name -> the names it is made of. */
const parts = new Map();

/**
 * Learns, from the book, which family and line names each catalog name is made of.
 * @param {import("./setup.js").RepertoireInfo[]} repertoires  The book, as the server sends it.
 */
export function indexOpenings(repertoires) {
  for (const repertoire of repertoires) {
    for (const variant of repertoire.variants) {
      if (!variant.opening) continue;
      const known = parts.get(variant.opening);
      // Several lines can end on the same named position: keep the best translated one.
      if (known && Object.keys(known.line).length >= Object.keys(variant.names).length) continue;
      parts.set(variant.opening, { family: repertoire.names, line: variant.names });
    }
  }
}

/**
 * The catalog name in the chosen language, or as it is when it cannot be translated.
 * @param {string} name  An English catalog name, as the server sends it.
 * @returns {string} The name to show.
 */
export function openingName(name) {
  const locale = getLocale();
  const entry = parts.get(name);
  if (!entry || locale === "en") return name;
  const { family, line } = entry;
  if (name === line.en) return line[locale] ?? (name === family.en ? family[locale] : undefined) ?? name;
  if (name === family.en) return family[locale] ?? name;
  const fits = name.startsWith(family.en) && name.endsWith(line.en) &&
    family.en.length + line.en.length < name.length;
  if (!fits || !family[locale]) return name;
  const separator = name.slice(family.en.length, name.length - line.en.length);
  if (line[locale]) return `${family[locale]}${separator}${line[locale]}`;
  // An untranslated line keeps its English name under the translated family, as in the tree,
  // unless the line's words are part of the family's ("Queen's Gambit Declined").
  return separator === ": " || separator === ", " ? `${family[locale]}${separator}${line.en}` : name;
}

/**
 * What a search over saved games looks in: the ECO and the opening in English and as shown.
 * @param {{eco?: string | null, opening?: string | null}} game  A saved game.
 * @returns {string} The text, lowercase.
 */
export function openingSearchText(game) {
  const opening = game.opening ?? "";
  return `${game.eco ?? ""} ${opening} ${opening ? openingName(opening) : ""}`.toLowerCase();
}
