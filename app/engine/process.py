"""One long-lived Stockfish process behind a lock: one search at a time (brief §9)."""

import asyncio
import logging
from pathlib import Path
from typing import Protocol

import chess
import chess.engine

from app.engine.levels import Level

logger = logging.getLogger(__name__)


class EngineUnavailableError(RuntimeError):
    """The engine could not produce a move, even after a restart."""


class MoveEngine(Protocol):
    """What the game layer needs from an engine; lets tests run without Stockfish."""

    name: str
    build_tag: str | None

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def play(self, board: chess.Board, level: Level) -> chess.Move: ...


class StockfishEngine:
    def __init__(self, path: str, threads: int, hash_mb: int, version_file: Path) -> None:
        self._path = path
        self._threads = threads
        self._hash_mb = hash_mb
        self._version_file = version_file
        self._engine: chess.engine.UciProtocol | None = None
        self._lock = asyncio.Lock()
        self.name = "unknown"
        self.build_tag: str | None = None

    async def start(self) -> None:
        _, self._engine = await chess.engine.popen_uci(self._path)
        await self._engine.configure({"Threads": self._threads, "Hash": self._hash_mb})
        self.name = self._engine.id.get("name", "unknown")
        if self._version_file.exists():
            self.build_tag = self._version_file.read_text(encoding="utf-8").strip()
        logger.info("engine started: %s (build %s)", self.name, self.build_tag)

    async def stop(self) -> None:
        if self._engine is not None:
            try:
                await asyncio.wait_for(self._engine.quit(), timeout=5)
            except (chess.engine.EngineError, TimeoutError):
                logger.warning("engine did not quit cleanly")
            self._engine = None

    async def play(self, board: chess.Board, level: Level) -> chess.Move:
        async with self._lock:
            try:
                return await self._search(board, level)
            except (chess.engine.EngineError, EngineUnavailableError) as error:
                logger.warning("engine failed (%s), restarting", error)
            try:
                await self.stop()
                await self.start()
                return await self._search(board, level)
            except (chess.engine.EngineError, OSError) as error:
                raise EngineUnavailableError(str(error)) from error

    async def _search(self, board: chess.Board, level: Level) -> chess.Move:
        if self._engine is None:
            raise EngineUnavailableError("engine is not running")
        result = await self._engine.play(board, level.limit, options=level.options)
        if result.move is None:
            raise EngineUnavailableError("engine returned no move")
        return result.move
