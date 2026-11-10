// Every button shows its name as a tooltip. Buttons with data-i18n-title get theirs from i18n.js;
// the others copy their accessible name (aria-label, else their text), and follow it when the
// text changes, in any language and for buttons added later.

/** @param {HTMLButtonElement} button */
function syncTitle(button) {
  if (button.hasAttribute("data-i18n-title")) return;
  const text = (button.getAttribute("aria-label") || button.textContent || "").trim();
  if (text && button.title !== text) button.title = text;
  if (!text && button.hasAttribute("title")) button.removeAttribute("title");
}

function syncAll() {
  for (const button of document.querySelectorAll("button")) syncTitle(button);
}

export function initTooltips() {
  let queued = false;
  const observer = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      syncAll();
    });
  });
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["aria-label"],
  });
  syncAll();
}
