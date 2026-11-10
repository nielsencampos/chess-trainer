"""The book's evaluations: loaded from `evals/book.json` and answered without the engine."""

import asyncio
import json

import chess
import pytest

from app.book.evaluate_book import book_positions
from app.book.sync import load_book_evals, sync_book_evals
from app.config import Settings
from app.db.connection import apply_migrations, open_database
from app.engine.evaluation import Evaluator

START = chess.Board().epd()


def write(path, positions):
    """Writes an evaluations file.

    Args:
        path (Path): The file.
        positions (dict): EPD -> evaluation.
    """
    path.write_text(json.dumps({"engine": "Test", "positions": positions}))


def test_sync_loads_the_file_once_and_replaces_rows(tmp_path):
    """Sync loads the file once and replaces rows.

    Args:
        tmp_path (Path): A temporary folder for this test.
    """
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
    """An engine that fails if it is ever asked, to prove the book answered."""

    async def evaluate(self, board, time_s):
        """Fails.

        Args:
            board (chess.Board): The position.
            time_s (float): The search time.

        Raises:
            LookupError: Always.
        """
        raise LookupError("asked the engine")


def test_a_book_position_never_reaches_the_engine():
    """A book position never reaches the engine."""
    evaluator = Evaluator(NoEngine(), {START: (25, None, "e2e4")})
    result = asyncio.run(evaluator.evaluate(chess.Board()))
    assert (result.cp, result.mate, result.best) == (25, None, "e2e4")
    # The same placement in Chess960 is not the book, so it goes to the engine.
    with pytest.raises(LookupError):
        asyncio.run(evaluator.evaluate(chess.Board.from_chess960_pos(518)))


def test_every_book_position_is_evaluated_deep():
    """Every book position is evaluated deep.

    A new or extended line needs `python -m app.book.evaluate_book` to be run again.
    """
    stored = json.loads(Settings().book_evals_file.read_text(encoding="utf-8"))["positions"]
    missing = [
        epd
        for epd in book_positions(Settings().openings_dir)
        if stored.get(epd, {}).get("depth", 0) < 32
    ]
    assert not missing, f"{len(missing)} book positions lack a depth-32 evaluation: {missing[:3]}"
