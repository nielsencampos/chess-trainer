// The two side bars: drag or use keys to resize, a button to hide and show. Kept per browser.

import { onLocaleChange, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

const KEY_STEP_PX = 20;
const BOARD_ROOM_PX = 368; // The smallest board plus the area's padding.

/**
 * @typedef {{key: "left" | "right", variable: string, bar: string, handle: string, toggle: string,
 *   min: number, max: number, initial: number}} SideBar
 */

/** @type {SideBar[]} */
const BARS = [
  {
    key: "left",
    variable: "--sidebar-width",
    bar: ".sidebar",
    handle: "resize-left",
    toggle: "toggle-left",
    min: 350,
    max: 700,
    initial: 380,
  },
  {
    key: "right",
    variable: "--movebar-width",
    bar: ".movebar",
    handle: "resize-right",
    toggle: "toggle-right",
    min: 350,
    max: 700,
    initial: 350,
  },
];

/** @param {string} id */
const byId = (id) => /** @type {any} */ (document.getElementById(id));

/**
 * @param {SideBar} bar
 * @param {unknown} width
 */
function clamp(bar, width) {
  const number = Number(width);
  if (!Number.isFinite(number)) return bar.initial;
  return Math.round(Math.min(bar.max, Math.max(bar.min, number)));
}

export function initLayout() {
  const shell = /** @type {HTMLElement} */ (document.querySelector(".app-shell"));
  /** @type {Record<string, {width: number, hidden: boolean}>} */
  const state = {};
  for (const bar of BARS) {
    state[bar.key] = {
      width: clamp(bar, getPref(`${bar.key}BarWidth`, bar.initial)),
      hidden: getPref(`${bar.key}BarHidden`, false) === true,
    };
  }

  /** @param {SideBar} bar */
  function apply(bar) {
    const { width, hidden } = state[bar.key];
    shell.style.setProperty(bar.variable, hidden ? "0px" : `${width}px`);
    /** @type {HTMLElement} */ (document.querySelector(bar.bar)).hidden = hidden;
    const handle = byId(bar.handle);
    handle.hidden = hidden;
    handle.setAttribute("aria-valuenow", String(width));
    const toggle = byId(bar.toggle);
    toggle.textContent = (bar.key === "left") !== hidden ? "◀" : "▶";
    const label = t(hidden ? `layout.show.${bar.key}` : `layout.hide.${bar.key}`);
    toggle.title = label;
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("aria-expanded", String(!hidden));
  }

  /**
   * @param {SideBar} bar
   * @param {number} width
   */
  function resize(bar, width) {
    const other = BARS.find((item) => item !== bar);
    const otherWidth = state[other.key].hidden ? 0 : state[other.key].width;
    const room = window.innerWidth - otherWidth - BOARD_ROOM_PX;
    state[bar.key].width = clamp(bar, Math.min(width, Math.max(room, bar.min)));
    apply(bar);
    setPref(`${bar.key}BarWidth`, state[bar.key].width);
  }

  for (const bar of BARS) {
    const handle = byId(bar.handle);
    handle.setAttribute("aria-valuemin", String(bar.min));
    handle.setAttribute("aria-valuemax", String(bar.max));

    handle.addEventListener("pointerdown", (/** @type {PointerEvent} */ event) => {
      handle.setPointerCapture(event.pointerId);
      document.body.classList.add("is-resizing");
      event.preventDefault();
    });
    handle.addEventListener("pointermove", (/** @type {PointerEvent} */ event) => {
      if (!handle.hasPointerCapture(event.pointerId)) return;
      resize(bar, bar.key === "left" ? event.clientX : window.innerWidth - event.clientX);
    });
    const stop = () => document.body.classList.remove("is-resizing");
    handle.addEventListener("pointerup", stop);
    handle.addEventListener("pointercancel", stop);
    handle.addEventListener("dblclick", () => resize(bar, bar.initial));
    handle.addEventListener("keydown", (/** @type {KeyboardEvent} */ event) => {
      const grow = bar.key === "left" ? "ArrowRight" : "ArrowLeft";
      const shrink = bar.key === "left" ? "ArrowLeft" : "ArrowRight";
      if (event.key === grow) resize(bar, state[bar.key].width + KEY_STEP_PX);
      else if (event.key === shrink) resize(bar, state[bar.key].width - KEY_STEP_PX);
      else return;
      event.preventDefault();
    });

    byId(bar.toggle).addEventListener("click", () => {
      state[bar.key].hidden = !state[bar.key].hidden;
      setPref(`${bar.key}BarHidden`, state[bar.key].hidden);
      apply(bar);
    });
    apply(bar);
  }
  const label = () => {
    for (const bar of BARS) {
      byId(bar.handle).setAttribute("aria-label", t(`layout.resize.${bar.key}`));
      apply(bar);
    }
  };
  label();
  onLocaleChange(label);
}
