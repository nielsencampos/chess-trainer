import random
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

from app.engine.levels import Level
from app.main import create_app


class FakeEngine:
    """Plays a scripted move when given one, otherwise the first legal move."""

    name = "Fake Engine 1"
    build_tag = "fake"

    def __init__(self) -> None:
        self.script: list[str] = []
        self.calls = 0

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def play(self, board: chess.Board, level: Level) -> chess.Move:
        self.calls += 1
        if self.script:
            return board.parse_san(self.script.pop(0))
        return next(iter(board.legal_moves))


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def client(engine):
    app = create_app(engine=engine, rng=random.Random(7))
    with TestClient(app) as test_client:
        yield test_client


def pytest_collection_modifyitems(items):
    for item in items:
        if Path(item.fspath).parent.name == "e2e":
            item.add_marker(pytest.mark.e2e)
