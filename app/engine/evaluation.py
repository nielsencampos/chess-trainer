"""Evaluation of a position for the bar next to the board, from White's side (brief §9)."""

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass

import chess
import chess.engine

from app.engine.process import MoveEngine

EVAL_TIME_S = 1.0
CACHE_SIZE = 4096


@dataclass(frozen=True)
class Evaluation:
    """Centipawns or moves to mate, from White's side. Mate 0 means the side to move is mated."""

    cp: int | None
    mate: int | None
    best: str | None


class Evaluator:
    def __init__(
        self, engine: MoveEngine, book: Mapping[str, tuple[int | None, int | None, str | None]]
    ) -> None:
        """`book`: EPD -> (cp, mate, best) of the book's positions, evaluated deep in advance."""
        self.engine = engine
        self.book = book
        self._cache: OrderedDict[tuple[str, bool], Evaluation] = OrderedDict()

    async def evaluate(self, board: chess.Board) -> Evaluation:
        key = (board.fen(), board.chess960)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        result = await self._evaluate(board)
        self._cache[key] = result
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return result

    async def _evaluate(self, board: chess.Board) -> Evaluation:
        # Finished positions need no engine, and some engines answer them oddly.
        if board.is_checkmate():
            winner_is_white = board.turn == chess.BLACK
            return Evaluation(cp=10_000 if winner_is_white else -10_000, mate=0, best=None)
        if board.is_game_over():
            return Evaluation(cp=0, mate=None, best=None)
        known = None if board.chess960 else self.book.get(board.epd())
        if known is not None:
            cp, mate, best = known
            return Evaluation(cp=None if mate is not None else cp, mate=mate, best=best)
        score, best = await self.engine.evaluate(board, EVAL_TIME_S)
        white = score.white()
        mate = white.mate()
        return Evaluation(
            cp=None if mate is not None else white.score(),
            mate=mate,
            best=best.uci() if best else None,
        )
