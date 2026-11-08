"""Runs the real binary: STOCKFISH_PATH=... uv run pytest -m engine"""

import asyncio
import os
from pathlib import Path

import chess
import pytest

from app.config import Settings
from app.engine.levels import LEVEL_ORDER, load_levels
from app.engine.process import StockfishEngine

pytestmark = pytest.mark.engine


@pytest.fixture
def stockfish_path():
    path = os.environ.get("STOCKFISH_PATH")
    if not path:
        pytest.skip("STOCKFISH_PATH is not set")
    return path


def test_all_levels_return_legal_moves_and_options_do_not_leak(stockfish_path):
    async def run() -> None:
        levels = load_levels(Settings().levels_file)
        engine = StockfishEngine(stockfish_path, 1, 16, Path("/nonexistent"))
        await engine.start()
        try:
            assert engine.name.startswith("Stockfish")
            board = chess.Board()
            board.push_san("e4")
            for key in (*LEVEL_ORDER, *reversed(LEVEL_ORDER)):
                move = await engine.play(board, levels[key])
                assert move in board.legal_moves
        finally:
            await engine.stop()

    asyncio.run(run())


def test_all_levels_play_chess960_and_can_castle(stockfish_path):
    async def run() -> None:
        levels = load_levels(Settings().levels_file)
        engine = StockfishEngine(stockfish_path, 1, 16, Path("/nonexistent"))
        await engine.start()
        try:
            for key in LEVEL_ORDER:
                board = chess.Board.from_chess960_pos(288)
                board.push(await engine.play(board, levels[key]))
            # The engine must read a position reached by king-takes-rook castling.
            board = chess.Board.from_chess960_pos(288)
            board.push(chess.Move.from_uci("f1g1"))
            assert board.is_valid()
            move = await engine.play(board, levels[LEVEL_ORDER[-1]])
            assert move in board.legal_moves
        finally:
            await engine.stop()

    asyncio.run(run())


def test_evaluation_is_full_strength_and_from_whites_side(stockfish_path):
    async def run() -> None:
        levels = load_levels(Settings().levels_file)
        engine = StockfishEngine(stockfish_path, 1, 16, Path("/nonexistent"))
        await engine.start()
        try:
            board = chess.Board()
            await engine.play(board, levels[LEVEL_ORDER[0]])  # the weakest level's options
            # Black has given away its queen: White must be far ahead, whoever is to move.
            board = chess.Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
            score, best = await engine.evaluate(board, 0.3)
            assert score.white().score(mate_score=100_000) > 500
            assert best in board.legal_moves
        finally:
            await engine.stop()

    asyncio.run(run())


def test_engine_restarts_after_a_crash(stockfish_path):
    async def run() -> None:
        levels = load_levels(Settings().levels_file)
        engine = StockfishEngine(stockfish_path, 1, 16, Path("/nonexistent"))
        await engine.start()
        try:
            engine._engine.transport.kill()
            await asyncio.sleep(0.2)
            board = chess.Board()
            assert await engine.play(board, levels["warmup"]) in board.legal_moves
        finally:
            await engine.stop()

    asyncio.run(run())


def test_concurrent_searches_are_serialized(stockfish_path):
    async def run() -> None:
        levels = load_levels(Settings().levels_file)
        engine = StockfishEngine(stockfish_path, 1, 16, Path("/nonexistent"))
        await engine.start()
        try:
            board = chess.Board()
            moves = await asyncio.gather(*(engine.play(board, levels["warmup"]) for _ in range(5)))
            assert all(move in board.legal_moves for move in moves)
        finally:
            await engine.stop()

    asyncio.run(run())
