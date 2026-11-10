// The chessboard: rendering, highlights, click and drag input, promotion picker.
// It knows nothing about the game: legal moves come in through `legalMoves`.

import { t } from "./i18n.js";

const FILES = "abcdefgh";
const DRAG_THRESHOLD_PX = 4;
const PROMOTION_PIECES = ["q", "r", "b", "n"];


/**
 * @typedef {{to: string, capture: boolean, promotion: boolean}} LegalMove
 * @typedef {{
 *   legalMoves: (square: string) => LegalMove[],
 *   onMove: (from: string, to: string, promotion?: string) => void,
 *   premoveTargets?: (square: string) => LegalMove[],
 *   onPremove?: (from: string, to: string) => void,
 *   onPremoveCancel?: () => void,
 * }} BoardCallbacks
 */

/**
 * Parses the piece placement field of a FEN.
 * @param {string} fen  The FEN.
 * @returns {Map<string, {color: "w" | "b", type: string}>} Square -> piece.
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

/** The chessboard: draws a position and turns clicks and drags into moves or premoves. */
export class Board {
  /**
   * Builds the squares and listens to the pointer.
   * @param {HTMLElement} root  The board's element.
   * @param {BoardCallbacks} callbacks  Where legal moves come from and where moves go.
   */
  constructor(root, callbacks) {
    this.root = root;
    this.callbacks = callbacks;
    this.orientation = "w";
    this.fen = "";
    /** @type {"w" | "b" | null} */
    this.movableColor = null;
    /** @type {"w" | "b" | null} */
    this.premoveColor = null;
    /** @type {string[]} */
    this.premoveSquares = [];
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
    root.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      if (this.premoveSquares.length > 0) this.callbacks.onPremoveCancel?.();
    });
    new ResizeObserver(() => this.updateSquareSize()).observe(root);
  }

  /**
   * Puts a color at the bottom.
   * @param {"w" | "b"} color  The color.
   * @returns {void}
   */
  setOrientation(color) {
    if (color === this.orientation) return;
    this.orientation = color;
    this.buildSquares();
    this.render();
  }

  /**
   * Shows a position, with its last move and check marked.
   * @param {string} fen  The position.
   * @param {{lastMove?: string[], check?: string | null}} [marks]  The last move's squares and
   *   the checked king's square.
   * @returns {void}
   */
  setPosition(fen, { lastMove = [], check = null } = {}) {
    this.fen = fen;
    this.lastMove = lastMove;
    this.checkSquare = check;
    this.clearSelection();
    this.render();
  }

  /**
   * Chooses whose pieces can be moved, or premoved, now.
   * @param {"w" | "b" | null} color  Whose pieces can be moved; null locks the board.
   * @param {"w" | "b" | null} [premoveColor]  Whose pieces can queue a premove meanwhile.
   * @returns {void}
   */
  setMovable(color, premoveColor = null) {
    this.movableColor = color;
    this.premoveColor = premoveColor;
    this.root.classList.toggle("can-move", this.activeColor !== null);
    if (this.activeColor === null) {
      this.clearSelection();
      this.closePromotion();
    }
    this.render();
  }

  /**
   * The color the user can act with now, for a move or a premove.
   * @returns {"w" | "b" | null} The color, or null when the board is locked.
   */
  get activeColor() {
    return this.movableColor ?? this.premoveColor;
  }

  /**
   * Marks the queued premove.
   * @param {string[]} squares  The queued premove's from and to, or nothing.
   * @returns {void}
   */
  setPremoveSquares(squares) {
    this.premoveSquares = squares;
    this.render();
  }

  /** Creates the 64 squares in the current orientation, with coordinates on the edge. */
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
   * A coordinate label.
   * @param {string} text  The file letter or rank number.
   * @param {string} className  `coord-file` or `coord-rank`.
   * @returns {HTMLSpanElement} The label.
   */
  coordinate(text, className) {
    const element = document.createElement("span");
    element.className = `coord ${className}`;
    element.textContent = text;
    return element;
  }

  /** Keeps the `--square-size` CSS variable in step with the board's width. */
  updateSquareSize() {
    this.root.style.setProperty("--square-size", `${this.root.clientWidth / 8}px`);
  }

  /** Draws the pieces and every highlight. */
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
      element.classList.toggle("movable", piece?.color === this.activeColor);
      element.classList.toggle("premove", this.premoveSquares.includes(name));
      element.dataset.piece = piece ? `${piece.color}${piece.type}` : "";
    }
  }

  /**
   * A Merida piece image.
   * @param {"w" | "b"} color  The piece's color.
   * @param {string} type  `p`, `n`, `b`, `r`, `q` or `k`.
   * @returns {HTMLElement} The image.
   */
  pieceElement(color, type) {
    const image = document.createElement("img");
    image.className = "piece";
    image.alt = `${color}${type}`;
    image.draggable = false;
    image.src = `pieces/merida/${color}${type.toUpperCase()}.svg`;
    return image;
  }

  /**
   * The square under the pointer.
   * @param {PointerEvent} event  The pointer event.
   * @returns {string | null} The square, or null outside the board.
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

  /**
   * Whether a square holds a piece the user can act with now.
   * @param {string} square  The square.
   * @returns {boolean} True if so.
   */
  isMovablePiece(square) {
    return this.activeColor !== null && parsePlacement(this.fen).get(square)?.color === this.activeColor;
  }

  /**
   * Selects a piece, or finishes a move on a target, and starts a possible drag.
   * @param {PointerEvent} event  The pointer event.
   * @returns {void}
   */
  onPointerDown(event) {
    if (event.button !== 0 || this.activeColor === null || this.promotion) return;
    const square = this.squareAt(event);
    if (!square) return;
    if (this.premoveSquares.length > 0) this.callbacks.onPremoveCancel?.();

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

  /**
   * Starts dragging once the pointer has moved far enough, then follows it.
   * @param {PointerEvent} event  The pointer event.
   * @returns {void}
   */
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

  /**
   * Drops a dragged piece, or unselects a piece clicked twice.
   * @param {PointerEvent} event  The pointer event.
   * @returns {void}
   */
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

  /** Abandons a press or drag, as when the browser cancels the pointer. */
  cancelPress() {
    if (this.press?.moved) this.stopDrag(this.press.square);
    this.press = null;
  }

  /**
   * Lifts a piece: a copy follows the pointer and the original fades.
   * @param {string} square  The piece's square.
   * @returns {void}
   */
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

  /**
   * Moves the dragged copy to the pointer.
   * @param {PointerEvent} event  The pointer event.
   * @returns {void}
   */
  moveGhost(event) {
    if (!this.ghost) return;
    this.ghost.style.left = `${event.clientX}px`;
    this.ghost.style.top = `${event.clientY}px`;
  }

  /**
   * Puts a dragged piece back.
   * @param {string} square  The piece's square.
   * @returns {void}
   */
  stopDrag(square) {
    this.ghost?.remove();
    this.ghost = null;
    this.squares.get(square)?.querySelector(".piece")?.classList.remove("is-dragged");
  }

  /**
   * Selects a piece and shows where it can go, for a move or a premove.
   * @param {string} square  The piece's square.
   * @returns {void}
   */
  select(square) {
    this.selected = square;
    this.targets = this.movableColor !== null
      ? this.callbacks.legalMoves(square)
      : (this.callbacks.premoveTargets?.(square) ?? []);
    this.render();
  }

  /** Unselects the piece and its targets, without drawing. */
  clearSelection() {
    this.selected = null;
    this.targets = [];
  }

  /**
   * Sends a move or a premove, or opens the promotion picker first.
   * @param {string} from  The piece's square.
   * @param {string} to  The target square.
   * @returns {void}
   */
  finishMove(from, to) {
    if (this.movableColor === null) {
      this.clearSelection();
      this.callbacks.onPremove?.(from, to);
      return;
    }
    const target = this.targets.find((candidate) => candidate.to === to);
    if (target?.promotion) {
      this.openPromotion(from, to);
      return;
    }
    this.clearSelection();
    this.callbacks.onMove(from, to);
  }

  /**
   * Shows the promotion picker over the target file.
   * @param {string} from  The pawn's square.
   * @param {string} to  The promotion square.
   * @returns {void}
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

  /** Removes the promotion picker, if open. */
  closePromotion() {
    this.promotion?.remove();
    this.promotion = null;
  }
}
