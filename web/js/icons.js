// Move icons: drawn for this app (GPL-3.0, like the rest of it), never copied from another site.
// A colored disc with a white glyph, so they read the same in the light and the dark theme. The
// move text itself is never colored.

const SVG = "http://www.w3.org/2000/svg";

/**
 * @typedef {"book" | "deviation" | "brilliant" | "great" | "best" | "excellent" | "good"
 *   | "inaccuracy" | "mistake" | "miss" | "blunder"} MoveIconKind
 */

/** Disc color, and a glyph that is either text or a path in a 20 x 20 box. */
const ICONS = /** @type {Record<MoveIconKind, {color: string, text?: string, path?: string}>} */ ({
  book: {
    color: "#9a7550",
    path: "M4.5 6.2c1.9-.9 3.7-.8 5.5.4 1.8-1.2 3.6-1.3 5.5-.4v8.2c-1.9-.8-3.7-.7-5.5.4-1.8-1.1-3.6-1.2-5.5-.4zM10 6.6v8.2",
  },
  deviation: {
    color: "#7a5bb5",
    path: "M7 16V10.5L4.5 8M7 10.5l5.5-5.5M12.5 5H9M12.5 5v3.5M13 16v-4",
  },
  brilliant: { color: "#1a9e94", text: "!!" },
  great: { color: "#4a7fc1", text: "!" },
  best: {
    color: "#5c9a3c",
    path: "M10 4.2l1.7 3.6 3.9.5-2.9 2.7.8 3.9-3.5-2-3.5 2 .8-3.9-2.9-2.7 3.9-.5z",
  },
  excellent: { color: "#6aa84a", path: "M5.6 10.4l2.9 2.9 5.9-6.1" },
  good: { color: "#8aa77a", path: "M6.2 10.4l2.6 2.6 5-5.2" },
  inaccuracy: { color: "#d4a72c", text: "?!" },
  mistake: { color: "#e07b2e", text: "?" },
  miss: { color: "#d4573a", path: "M7 7l6 6M13 7l-6 6" },
  blunder: { color: "#c2382b", text: "??" },
});

export const MOVE_ICON_KINDS = /** @type {MoveIconKind[]} */ (Object.keys(ICONS));

/**
 * @param {MoveIconKind} kind
 * @param {string} label  What a screen reader says, already translated.
 * @returns {SVGSVGElement}
 */
export function moveIcon(kind, label) {
  const icon = ICONS[kind];
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("class", `move-icon move-icon-${kind}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", label);
  const disc = document.createElementNS(SVG, "circle");
  disc.setAttribute("cx", "10");
  disc.setAttribute("cy", "10");
  disc.setAttribute("r", "10");
  disc.setAttribute("fill", icon.color);
  svg.append(disc);
  if (icon.path) {
    const path = document.createElementNS(SVG, "path");
    path.setAttribute("d", icon.path);
    const filled = kind === "best";
    path.setAttribute("fill", filled ? "#fff" : "none");
    path.setAttribute("stroke", "#fff");
    path.setAttribute("stroke-width", filled ? "0.8" : "1.7");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.append(path);
  } else {
    const text = document.createElementNS(SVG, "text");
    text.setAttribute("x", "10");
    text.setAttribute("y", "14.3");
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#fff");
    text.setAttribute("font-size", (icon.text ?? "").length > 1 ? "11" : "12.5");
    text.setAttribute("font-weight", "800");
    text.setAttribute("letter-spacing", "-0.5");
    text.textContent = icon.text ?? "";
    svg.append(text);
  }
  return svg;
}
