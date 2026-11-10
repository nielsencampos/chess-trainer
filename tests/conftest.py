"""Shared fixtures: a fake engine, the book loaded once, and an API client per test."""

import dataclasses
import random
import shutil
from pathlib import Path

import chess
import chess.engine
import pytest
from fastapi.testclient import TestClient

from app.book.sync import sync_catalog, sync_openings
from app.config import Settings
from app.db.connection import apply_migrations, open_database
from app.engine.levels import Level
from app.main import create_app

# Tests never read the generated evaluations, so the fake engine answers every position.
NO_BOOK_EVALS = Path("/nonexistent/book.json")


class FakeEngine:
    """Plays a scripted move when given one, otherwise the first legal move.

    Attributes:
        script (list[str]): SAN moves to play next, in order.
        calls (int): How many times `play` was called.
        last_max_time_s (float | None): The time limit of the last search.
    """

    name = "Fake Engine 1"
    build_tag = "fake"

    def __init__(self) -> None:
        """Creates an engine with an empty script."""
        self.script: list[str] = []
        self.calls = 0
        self.last_max_time_s: float | None = None

    async def start(self) -> None:
        """Does nothing: there is no process."""
        pass

    async def stop(self) -> None:
        """Does nothing: there is no process."""
        pass

    async def play(
        self, board: chess.Board, level: Level, max_time_s: float | None = None
    ) -> chess.Move:
        """Plays the next scripted move, or the first legal move.

        Args:
            board (chess.Board): The position.
            level (Level): Ignored.
            max_time_s (float | None): Recorded in `last_max_time_s`.

        Returns:
            chess.Move: The move.
        """
        self.calls += 1
        self.last_max_time_s = max_time_s
        if self.script:
            return board.parse_san(self.script.pop(0))
        return next(iter(board.legal_moves))

    async def evaluate(self, board: chess.Board, time_s: float):
        """Material from White's side, so tests can tell positions apart.

        Args:
            board (chess.Board): The position.
            time_s (float): Ignored.

        Returns:
            tuple[chess.engine.PovScore, chess.Move | None]: The material and the first legal
                move.
        """
        self.evaluations = getattr(self, "evaluations", 0) + 1
        values = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300, chess.ROOK: 500}
        values[chess.QUEEN] = 900
        material = sum(
            value * (len(board.pieces(piece, chess.WHITE)) - len(board.pieces(piece, chess.BLACK)))
            for piece, value in values.items()
        )
        best = next(iter(board.legal_moves), None)
        return chess.engine.PovScore(chess.engine.Cp(material), chess.WHITE), best


@pytest.fixture
def engine() -> FakeEngine:
    """A fake engine for one test.

    Returns:
        FakeEngine: The engine.
    """
    return FakeEngine()


@pytest.fixture(scope="session")
def loaded_database(tmp_path_factory) -> Path:
    """A database with the book loaded once: the load is too slow to repeat per test.

    Args:
        tmp_path_factory (pytest.TempPathFactory): pytest's session temporary folders.

    Returns:
        Path: The database file.
    """
    path = tmp_path_factory.mktemp("db") / "test.duckdb"
    connection = open_database(path)
    apply_migrations(connection)
    sync_openings(connection, Settings().openings_dir)
    sync_catalog(connection, Settings().catalog_dir)
    connection.close()
    return path


@pytest.fixture
def database_path(loaded_database, tmp_path) -> Path:
    """A copy of the loaded database per test, because games are saved in it.

    Args:
        loaded_database (Path): The session's database.
        tmp_path (Path): This test's temporary folder.

    Returns:
        Path: The copy.
    """
    path = tmp_path / "test.duckdb"
    shutil.copy(loaded_database, path)
    return path


@pytest.fixture
def client(engine, database_path):
    """The app on this test's database and the fake engine, with a seeded random source.

    Args:
        engine (FakeEngine): The fake engine.
        database_path (Path): This test's database.

    Yields:
        TestClient: The API client, with the app started.
    """
    settings = dataclasses.replace(
        Settings(), database_path=database_path, book_evals_file=NO_BOOK_EVALS
    )
    app = create_app(settings, engine=engine, rng=random.Random(7))
    with TestClient(app) as test_client:
        yield test_client


def pytest_collection_modifyitems(items):
    """Marks every test in `tests/e2e/` as `e2e`, so plain `pytest` skips them.

    Args:
        items (list[pytest.Item]): The collected tests.
    """
    for item in items:
        if Path(item.fspath).parent.name == "e2e":
            item.add_marker(pytest.mark.e2e)
