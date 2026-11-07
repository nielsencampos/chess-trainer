import dataclasses
import random
import shutil
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

from app.book.sync import sync_catalog, sync_openings
from app.config import Settings
from app.db.connection import apply_migrations, open_database
from app.engine.levels import Level
from app.main import create_app


class FakeEngine:
    """Plays a scripted move when given one, otherwise the first legal move."""

    name = "Fake Engine 1"
    build_tag = "fake"

    def __init__(self) -> None:
        self.script: list[str] = []
        self.calls = 0
        self.last_max_time_s: float | None = None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def play(
        self, board: chess.Board, level: Level, max_time_s: float | None = None
    ) -> chess.Move:
        self.calls += 1
        self.last_max_time_s = max_time_s
        if self.script:
            return board.parse_san(self.script.pop(0))
        return next(iter(board.legal_moves))


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture(scope="session")
def loaded_database(tmp_path_factory) -> Path:
    """A database with the book loaded once: the load is too slow to repeat per test."""
    path = tmp_path_factory.mktemp("db") / "test.duckdb"
    connection = open_database(path)
    apply_migrations(connection)
    sync_openings(connection, Settings().openings_dir)
    sync_catalog(connection, Settings().catalog_dir)
    connection.close()
    return path


@pytest.fixture
def database_path(loaded_database, tmp_path) -> Path:
    """A copy per test, because games are saved in it."""
    path = tmp_path / "test.duckdb"
    shutil.copy(loaded_database, path)
    return path


@pytest.fixture
def client(engine, database_path):
    settings = dataclasses.replace(Settings(), database_path=database_path)
    app = create_app(settings, engine=engine, rng=random.Random(7))
    with TestClient(app) as test_client:
        yield test_client


def pytest_collection_modifyitems(items):
    for item in items:
        if Path(item.fspath).parent.name == "e2e":
            item.add_marker(pytest.mark.e2e)
