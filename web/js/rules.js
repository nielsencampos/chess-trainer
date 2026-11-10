// The rules of chess in the browser, for instant feedback. The server remains the source of truth.
// Squares and promotions use the app's notation ("e4", "q"), and only this file knows chessops.

import { castlingSide, Chess, normalizeMove } from "./vendor/chessops/chess.js";
import { makeFen, parseFen } from "./vendor/chessops/fen.js";
import { makeSan, parseSan } from "./vendor/chessops/san.js";
import {
  charToRole,
  kingCastlesTo,
  makeSquare,
  makeUci,
  parseSquare,
  roleToChar,
  squareRank,
} from "./vendor/chessops/util.js";

const FIFTY_MOVES_IN_HALFMOVES = 100;
const REPETITIONS_TO_END = 3;

/**
 * @typedef {{to: string, capture: boolean, promotion: boolean}} TargetMove
 * @typedef {{san: string, uci: string, capture: boolean, castle: boolean}} PlayedMove
 */

/**
 * The squares strictly between two squares of the same rank.
 * @param {number} a  A square, as chessops numbers them.
 * @param {number} b  Another square.
 * @returns {number[]} The squares, in order.
 */
function squaresBetween(a, b) {
  const squares = [];
  for (let square = Math.min(a, b) + 1; square < Math.max(a, b); square += 1) squares.push(square);
  return squares;
}

/** The position of one game in the browser: legal moves, check, game over and repetitions. */
export class Rules {
  /**
   * Starts from the standard position, or from a Chess960 one.
   * @param {string} [chess960Fen]  The starting position of a Chess960 game.
   */
  constructor(chess960Fen) {
    this.chess960 = chess960Fen !== undefined;
    this.position = this.chess960
      ? Chess.fromSetup(parseFen(/** @type {string} */ (chess960Fen)).unwrap()).unwrap()
      : Chess.default();
    /** @type {Map<string, number>} */
    this.seen = new Map();
    this.countPosition();
  }

  /**
   * The position as FEN.
   * @returns {string} The FEN.
   */
  fen() {
    return makeFen(this.position.toSetup());
  }

  /**
   * The piece on a square.
   * @param {string} square  The square, such as `e4`.
   * @returns {{color: "w" | "b", type: string} | null} The piece, or null if empty.
   */
  pieceAt(square) {
    const piece = this.position.board.get(/** @type {number} */ (parseSquare(square)));
    if (!piece) return null;
    return { color: piece.color === "white" ? "w" : "b", type: roleToChar(piece.role) };
  }

  /**
   * Legal destinations of the piece on a square. Castling is the king's two-square move, or in
   * Chess960 the rook and any square between it and the king that is not a normal king move.
   * @param {string} square  The piece's square.
   * @returns {TargetMove[]} The destinations, marked as captures or promotions.
   */
  movesFrom(square) {
    const from = /** @type {number} */ (parseSquare(square));
    const { position } = this;
    const isPawn = position.board.pawn.has(from);
    const dests = position.dests(from);
    return [...dests].flatMap((to) => {
      const side = castlingSide(position, { from, to });
      if (side && this.chess960) {
        return [to, ...squaresBetween(from, to).filter((square) => !dests.has(square))].map(
          (square) => ({ to: makeSquare(square), capture: false, promotion: false }),
        );
      }
      if (side) {
        const kingTo = kingCastlesTo(position.turn, side);
        return { to: makeSquare(kingTo), capture: false, promotion: false };
      }
      return {
        to: makeSquare(to),
        capture: position.board.occupied.has(to) || (isPawn && position.epSquare === to),
        promotion: isPawn && (squareRank(to) === 0 || squareRank(to) === 7),
      };
    });
  }

  /**
   * Plays a move if it is legal.
   * @param {string} from  The piece's square.
   * @param {string} to  The square clicked.
   * @param {string} [promotion]  The piece to promote to: `q`, `r`, `b` or `n`.
   * @returns {PlayedMove | null}  `uci` is what the server expects, whichever square was clicked;
   *   null if the move is illegal.
   */
  move(from, to, promotion) {
    const move = {
      from: /** @type {number} */ (parseSquare(from)),
      to: /** @type {number} */ (parseSquare(to)),
      promotion: promotion ? charToRole(promotion) : undefined,
    };
    // chessops' play() does not validate, so an illegal move would corrupt the position. Its
    // isLegal() also takes king-takes-rook castling, which the server refuses in a normal game.
    const offered = this.movesFrom(from).some((target) => target.to === to);
    if (offered && this.chess960) {
      move.to = this.chess960CastlingRook(move.from, move.to) ?? move.to;
    }
    if (!offered || !this.position.isLegal(move)) return null;
    return this.play(normalizeMove(this.position, move), move.promotion);
  }

  /**
   * Plays a move the server sent. A move it cannot parse means the two sides disagree.
   * @param {string} san  The move in SAN.
   * @returns {PlayedMove} The move played.
   * @throws {Error} The move is illegal here.
   */
  moveSan(san) {
    const move = parseSan(this.position, san);
    if (!move) throw new Error(`illegal move from the server: ${san}`);
    return this.play(move, /** @type {any} */ (move).promotion);
  }

  /**
   * The rook a click on `to` castles with, if it is a castling target.
   * @param {number} from  The king's square.
   * @param {number} to  The square clicked.
   * @returns {number | undefined} The rook's square, or undefined if it is not castling.
   */
  chess960CastlingRook(from, to) {
    const dests = this.position.dests(from);
    return [...dests].find(
      (rook) =>
        castlingSide(this.position, { from, to: rook }) !== undefined &&
        (rook === to || (squaresBetween(from, rook).includes(to) && !dests.has(to))),
    );
  }

  /**
   * Whether the side to move is in check.
   * @returns {boolean} True in check.
   */
  isCheck() {
    return this.position.isCheck();
  }

  /**
   * The square of the king in check.
   * @returns {string | null} The square, or null when there is no check.
   */
  checkSquare() {
    if (!this.isCheck()) return null;
    const king = this.position.board.kingOf(this.position.turn);
    return king === undefined ? null : makeSquare(king);
  }

  /**
   * Whether the game is over, including the draws the server applies by itself: threefold
   * repetition and fifty moves.
   * @returns {boolean} True if it is over.
   */
  isGameOver() {
    return (
      this.position.isEnd() ||
      this.position.halfmoves >= FIFTY_MOVES_IN_HALFMOVES ||
      (this.seen.get(this.repetitionKey()) ?? 0) >= REPETITIONS_TO_END
    );
  }

  /**
   * Plays a legal move and counts the new position for repetitions.
   * @param {any} move  A legal move, with castling as king takes rook.
   * @param {any} promotion  The chessops role to promote to, if any.
   * @returns {PlayedMove} The move, with the UCI the server expects.
   */
  play(move, promotion) {
    const { position } = this;
    const side = castlingSide(position, move);
    const castle = side !== undefined;
    const capture =
      !castle &&
      (position.board.occupied.has(move.to) ||
        (position.board.pawn.has(move.from) && position.epSquare === move.to));
    const legalMove = { from: move.from, to: move.to, promotion };
    const san = makeSan(position, legalMove);
    const uci =
      side && !this.chess960
        ? makeUci({ from: move.from, to: kingCastlesTo(position.turn, side) })
        : makeUci(legalMove);
    position.play(legalMove);
    this.countPosition();
    return { san, uci, capture, castle };
  }

  /**
   * Piece placement, turn, castling rights and en passant, as the rule compares positions.
   * @returns {string} The first four fields of the FEN.
   */
  repetitionKey() {
    return this.fen().split(" ").slice(0, 4).join(" ");
  }

  /** Counts the current position once more, for threefold repetition. */
  countPosition() {
    const key = this.repetitionKey();
    this.seen.set(key, (this.seen.get(key) ?? 0) + 1);
  }
}
