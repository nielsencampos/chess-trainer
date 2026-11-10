/** The bot's level names, with the nominal rating each level shows beside its name. */

import { t } from "./i18n.js";

/** @type {Record<string, string>} The nominal rating of each level, by key. */
let ratings = {};

/**
 * Keeps the levels' nominal ratings, as the levels endpoint sends them.
 * @param {Record<string, string> | undefined} elo  The rating of each level, by key.
 * @returns {void}
 */
export function setLevelRatings(elo) {
  ratings = elo ?? {};
}

/**
 * The level's name in the current language, with its rating when it has one.
 * @param {string} key  The level's key.
 * @returns {string} Such as "Club (1320)".
 */
export function levelLabel(key) {
  const name = t(`level.${key}`);
  const elo = ratings[key];
  return elo ? t("level.label", { name, elo }) : name;
}
