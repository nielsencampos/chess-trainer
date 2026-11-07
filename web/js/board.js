// The chessboard: rendering, highlights, click and drag input, promotion picker.
// It knows nothing about the game: legal moves come in through `legalMoves`.

import { t } from "./i18n.js";

const FILES = "abcdefgh";
const DRAG_THRESHOLD_PX = 4;
const PROMOTION_PIECES = ["q", "r", "b", "n"];
const UNICODE_GLYPHS = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };

export const PIECE_SETS = ["merida", "cburnett", "chessnut", "fantasy", "unicode"];

/**
 * @typedef {{to: string, capture: boolean, promotion: boolean}} LegalMove
 * @typedef {{
 *   legalMoves: (square: string) => LegalMove[],
 *   onMove: (from: string, to: string, promotion?: string) => void,
 * }} BoardCallbacks
 */

/**
 * Parses the piece placement field of a FEN.
 * @param {string} fen
 * @returns {Map<string, {color: "w" | "b", type: string}>}
 */
function parsePlacement(fen) {
  const pieces = new Map();
  fen.split(" ")[0].split("/").forEach((row, rowIndex) => {
    let file = 0;
    for (const char of row) {
      if (/\d/.test(char)) {
        file += Number(char);
      } else {
        const color = char === char.toUpperCase() ? "w" : "b";
        pieces.set(`${FILES[file]}${8 - rowIndex}`, { color, type: char.toLowerCase() });
        file += 1;
      }
    }
  });
  return pieces;
}

export class Board {
  /**
   * @param {HTMLElement} root
   * @param {BoardCallbacks} callbacks
   * @param {string} pieceSet
   */
  constructor(root, callbacks, pieceSet = "cburnett") {
    this.root = root;
    this.callbacks = callbacks;
    this.pieceSet = pieceSet;
    this.orientation = "w";
    this.fen = "";
    /** @type {"w" | "b" | null} */
    this.movableColor = null;
    /** @type {string[]} */
    this.lastMove = [];
    /** @type {string | null} */
    this.checkSquare = null;
    /** @type {string | null} */
    this.selected = null;
    /** @type {LegalMove[]} */
    this.targets = [];
    /** @type {{square: string, x: number, y: number, moved: boolean, wasSelected: boolean} | null} */
    this.press = null;
    /** @type {HTMLElement | null} */
    this.ghost = null;
    /** @type {HTMLElement | null} */
    this.promotion = null;
    /** @type {Map<string, HTMLElement>} */
    this.squares = new Map();

    this.buildSquares();
    root.addEventListener("pointerdown", (event) => this.onPointerDown(event));
    root.addEventListener("pointermove", (event) => this.onPointerMove(event));
    root.addEventListener("pointerup", (event) => this.onPointerUp(event));
    root.addEventListener("pointercancel", () => this.cancelPress());
    root.addEventListener("contextmenu", (event) => event.preventDefault());
    new ResizeObserver(() => this.updateSquareSize()).observe(root);
  }

  /** @param {"w" | "b"} color */
  setOrientation(color) {
    if (color === this.orientation) return;
    this.orientation = color;
    this.buildSquares();
    this.render();
  }

  /** @param {string} pieceSet */
  setPieceSet(pieceSet) {
    this.pieceSet = pieceSet;
    this.render();
  }

  /**
   * @param {string} fen
   * @param {{lastMove?: string[], check?: string | null}} [marks]
   */
  setPosition(fen, { lastMove = [], check = null } = {}) {
    this.fen = fen;
    this.lastMove = lastMove;
    this.checkSquare = check;
    this.clearSelection();
    this.render();
  }

  /** @param {"w" | "b" | null} color  Whose pieces can be moved; null locks the board. */
  setMovable(color) {
    this.movableColor = color;
    this.root.classList.toggle("can-move", color !== null);
    if (color === null) {
      this.clearSelection();
      this.closePromotion();
    }
    this.render();
  }

  buildSquares() {
    this.root.querySelectorAll(".square").forEach((element) => element.remove());
    this.squares.clear();
    const ranks = this.orientation === "w" ? [8, 7, 6, 5, 4, 3, 2, 1] : [1, 2, 3, 4, 5, 6, 7, 8];
    const files = this.orientation === "w" ? [...FILES] : [...FILES].reverse();
    const fragment = document.createDocumentFragment();
    ranks.forEach((rank, row) => {
      files.forEach((file, column) => {
        const name = `${file}${rank}`;
        const element = document.createElement("div");
        const isLight = (FILES.indexOf(file) + rank) % 2 === 0;
        element.className = `square ${isLight ? "light" : "dark"}`;
        element.dataset.square = name;
        if (column === 0) element.append(this.coordinate(String(rank), "coord-rank"));
        if (row === 7) element.append(this.coordinate(file, "coord-file"));
        this.squares.set(name, element);
        fragment.append(element);
      });
    });
    this.root.prepend(fragment);
  }

  /**
   * @param {string} text
   * @param {string} className
   */
  coordinate(text, className) {
    const element = document.createElement("span");
    element.className = `coord ${className}`;
    element.textContent = text;
    return element;
  }

  updateSquareSize() {
    this.root.style.setProperty("--square-size", `${this.root.clientWidth / 8}px`);
  }

  render() {
    const pieces = parsePlacement(this.fen || "8/8/8/8/8/8/8/8 w - - 0 1");
    const targetsByTo = new Map(this.targets.map((target) => [target.to, target]));
    for (const [name, element] of this.squares) {
      element.querySelector(".piece")?.remove();
      const piece = pieces.get(name);
      if (piece) element.append(this.pieceElement(piece.color, piece.type));
      const target = targetsByTo.get(name);
      element.classList.toggle("last", this.lastMove.includes(name));
      element.classList.toggle("selected", this.selected === name);
      element.classList.toggle("check", this.checkSquare === name);
      element.classList.toggle("target", target !== undefined && !target.capture);
      element.classList.toggle("capture", target !== undefined && target.capture);
      element.classList.toggle("movable", piece?.color === this.movableColor);
      element.dataset.piece = piece ? `${piece.color}${piece.type}` : "";
    }
  }

  /**
   * @param {"w" | "b"} color
   * @param {string} type
   * @returns {HTMLElement}
   */
  pieceElement(color, type) {
    if (this.pieceSet === "unicode") {
      const glyph = document.createElement("span");
      glyph.className = `piece piece-glyph ${color === "w" ? "white" : "black"}`;
      glyph.textContent = `${UNICODE_GLYPHS[type]}︎`;
      return glyph;
    }
    const image = document.createElement("img");
    image.className = "piece";
    image.alt = `${color}${type}`;
    image.draggable = false;
    image.src = `pieces/${this.pieceSet}/${color}${type.toUpperCase()}.svg`;
    return image;
  }

  /**
   * @param {PointerEvent} event
   * @returns {string | null}
   */
  squareAt(event) {
    const box = this.root.getBoundingClientRect();
    const column = Math.floor(((event.clientX - box.left) / box.width) * 8);
    const row = Math.floor(((event.clientY - box.top) / box.height) * 8);
    if (column < 0 || column > 7 || row < 0 || row > 7) return null;
    return this.orientation === "w"
      ? `${FILES[column]}${8 - row}`
      : `${FILES[7 - column]}${row + 1}`;
  }

  /** @param {string} square */
  isMovablePiece(square) {
    return this.movableColor !== null && parsePlacement(this.fen).get(square)?.color === this.movableColor;
  }

  /** @param {PointerEvent} event */
  onPointerDown(event) {
    if (event.button !== 0 || this.movableColor === null || this.promotion) return;
    const square = this.squareAt(event);
    if (!square) return;

    if (this.selected && this.targets.some((target) => target.to === square)) {
      this.finishMove(this.selected, square);
      return;
    }
    if (!this.isMovablePiece(square)) {
      this.clearSelection();
      this.render();
      return;
    }
    const wasSelected = this.selected === square;
    this.select(square);
    this.press = { square, x: event.clientX, y: event.clientY, moved: false, wasSelected };
    this.root.setPointerCapture(event.pointerId);
    event.preventDefault();
  }

  /** @param {PointerEvent} event */
  onPointerMove(event) {
    if (!this.press) return;
    if (!this.press.moved) {
      const distance = Math.hypot(event.clientX - this.press.x, event.clientY - this.press.y);
      if (distance < DRAG_THRESHOLD_PX) return;
      this.press.moved = true;
      this.startDrag(this.press.square);
    }
    this.moveGhost(event);
  }

  /** @param {PointerEvent} event */
  onPointerUp(event) {
    if (!this.press) return;
    const { square, moved, wasSelected } = this.press;
    this.press = null;
    if (moved) {
      this.stopDrag(square);
      const to = this.squareAt(event);
      if (to && this.targets.some((target) => target.to === to)) {
        this.finishMove(square, to);
      } else if (to !== square) {
        this.clearSelection();
        this.render();
      }
    } else if (wasSelected) {
      this.clearSelection();
      this.render();
    }
  }

  cancelPress() {
    if (this.press?.moved) this.stopDrag(this.press.square);
    this.press = null;
  }

  /** @param {string} square */
  startDrag(square) {
    const piece = this.squares.get(square)?.querySelector(".piece");
    if (!piece) return;
    this.ghost = document.createElement("div");
    this.ghost.className = "drag-ghost";
    const size = this.root.clientWidth / 8;
    this.ghost.style.width = `${size}px`;
    this.ghost.style.height = `${size}px`;
    this.ghost.style.setProperty("--square-size", `${size}px`);
    this.ghost.append(piece.cloneNode(true));
    document.body.append(this.ghost);
    piece.classList.add("is-dragged");
  }

  /** @param {PointerEvent} event */
  moveGhost(event) {
    if (!this.ghost) return;
    this.ghost.style.left = `${event.clientX}px`;
    this.ghost.style.top = `${event.clientY}px`;
  }

  /** @param {string} square */
  stopDrag(square) {
    this.ghost?.remove();
    this.ghost = null;
    this.squares.get(square)?.querySelector(".piece")?.classList.remove("is-dragged");
  }

  /** @param {string} square */
  select(square) {
    this.selected = square;
    this.targets = this.callbacks.legalMoves(square);
    this.render();
  }

  clearSelection() {
    this.selected = null;
    this.targets = [];
  }

  /**
   * @param {string} from
   * @param {string} to
   */
  finishMove(from, to) {
    const target = this.targets.find((candidate) => candidate.to === to);
    if (target?.promotion) {
      this.openPromotion(from, to);
      return;
    }
    this.clearSelection();
    this.callbacks.onMove(from, to);
  }

  /**
   * @param {string} from
   * @param {string} to
   */
  openPromotion(from, to) {
    const color = parsePlacement(this.fen).get(from)?.color ?? "w";
    const backdrop = document.createElement("div");
    backdrop.className = "promotion-backdrop";
    const picker = document.createElement("div");
    picker.className = "promotion";
    picker.setAttribute("role", "group");
    picker.setAttribute("aria-label", t("board.promotion"));
    const column = this.orientation === "w" ? FILES.indexOf(to[0]) : 7 - FILES.indexOf(to[0]);
    picker.style.left = `${column * 12.5}%`;
    for (const type of PROMOTION_PIECES) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.promotion = type;
      button.append(this.pieceElement(color, type));
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        this.closePromotion();
        this.clearSelection();
        this.callbacks.onMove(from, to, type);
      });
      picker.append(button);
    }
    // Pointer events would otherwise reach the board handlers underneath.
    backdrop.addEventListener("pointerdown", (event) => event.stopPropagation());
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) {
        this.closePromotion();
        this.clearSelection();
        this.render();
      }
    });
    backdrop.append(picker);
    this.root.append(backdrop);
    this.promotion = backdrop;
    picker.querySelector("button")?.focus();
  }

  closePromotion() {
    this.promotion?.remove();
    this.promotion = null;
  }
}
