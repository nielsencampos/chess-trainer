import asyncio
import json

import chess
import pytest

from app.book.sync import load_book_evals, sync_book_evals
from app.db.connection import apply_migrations, open_database
from app.engine.evaluation import Evaluator

START = chess.Board().epd()


def write(path, positions):
    path.write_text(json.dumps({"engine": "Test", "positions": positions}))


def test_sync_loads_the_file_once_and_replaces_rows(tmp_path):
    connection = open_database(tmp_path / "db.duckdb")
    apply_migrations(connection)
    evals = tmp_path / "book.json"
    assert sync_book_evals(connection, evals) is False  # no file yet
    write(evals, {START: {"cp": 20, "best": "e2e4", "depth": 20}})
    assert sync_book_evals(connection, evals) is True
    assert sync_book_evals(connection, evals) is False  # unchanged
    write(evals, {START: {"cp": 25, "best": "e2e4", "depth": 32}})
    assert sync_book_evals(connection, evals) is True
    assert load_book_evals(connection) == {START: (25, None, "e2e4")}


class NoEngine:
    async def evaluate(self, board, time_s):
        raise LookupError("asked the engine")


def test_a_book_position_never_reaches_the_engine():
    evaluator = Evaluator(NoEngine(), {START: (25, None, "e2e4")})
    result = asyncio.run(evaluator.evaluate(chess.Board()))
    assert (result.cp, result.mate, result.best) == (25, None, "e2e4")
    # The same placement in Chess960 is not the book, so it goes to the engine.
    with pytest.raises(LookupError):
        asyncio.run(evaluator.evaluate(chess.Board.from_chess960_pos(518)))
