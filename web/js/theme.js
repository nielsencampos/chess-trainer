import { t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

const THEMES = ["auto", "light", "dark"];

/** @param {string} theme */
function apply(theme) {
  if (theme === "auto") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
}

/** @param {HTMLButtonElement} button */
export function initTheme(button) {
  let theme = getPref("theme", "auto");
  if (!THEMES.includes(theme)) theme = "auto";
  const render = () => {
    apply(theme);
    button.textContent = t(`theme.${theme}`);
  };
  render();
  button.addEventListener("click", () => {
    theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    setPref("theme", theme);
    render();
  });
}
