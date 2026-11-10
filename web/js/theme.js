// Light and dark theme: follows the system, with a button that cycles auto, light and dark.

import { onLocaleChange, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

const THEMES = ["auto", "light", "dark"];

/**
 * Sets the theme on the page.
 * @param {string} theme  `auto` (follow the system), `light` or `dark`.
 */
function apply(theme) {
  if (theme === "auto") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
}

/**
 * Wires the theme button, restoring the stored choice.
 * @param {HTMLButtonElement} button  The button that cycles the theme and shows the current one.
 */
export function initTheme(button) {
  let theme = getPref("theme", "auto");
  if (!THEMES.includes(theme)) theme = "auto";
  /** Applies the theme and labels the button in the current language. */
  const render = () => {
    apply(theme);
    button.textContent = t(`theme.${theme}`);
  };
  render();
  onLocaleChange(render);
  button.addEventListener("click", () => {
    theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    setPref("theme", theme);
    render();
  });
}
