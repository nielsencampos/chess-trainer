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
    """What the game layer needs from an engine; lets tests run without Stockfish.

    Attributes:
        name (str): The engine's name, as it reports it.
        build_tag (str | None): The release tag of the build, if known.
    """

    name: str
    build_tag: str | None

    async def start(self) -> None:
        """Starts the engine process."""
        ...

    async def stop(self) -> None:
        """Stops the engine process."""
        ...

    async def play(
        self, board: chess.Board, level: Level, max_time_s: float | None = None
    ) -> chess.Move:
        """Chooses the bot's move.

        Args:
            board (chess.Board): The position, with the bot to move.
            level (Level): The strength to play at.
            max_time_s (float | None): The most the search may take, from the bot's clock.

        Returns:
            chess.Move: The move.
        """
        ...

    async def evaluate(
        self, board: chess.Board, time_s: float
    ) -> tuple[chess.engine.PovScore, chess.Move | None]:
        """Evaluates a position at full strength.

        Args:
            board (chess.Board): The position.
            time_s (float): How long to search, in seconds.

        Returns:
            tuple[chess.engine.PovScore, chess.Move | None]: The score and the best move, if any.
        """
        ...


def limit_for(level: Level, max_time_s: float | None) -> chess.engine.Limit:
    """The level's limit, shortened when the bot's clock has less time than the level would use.

    Args:
        level (Level): The strength level.
        max_time_s (float | None): The most the search may take, or None for no clock.

    Returns:
        chess.engine.Limit: The search limit.
    """
    if max_time_s is None:
        return level.limit
    level_time = level.limit.time
    time = max_time_s if level_time is None else min(level_time, max_time_s)
    return chess.engine.Limit(time=time, depth=level.limit.depth, nodes=level.limit.nodes)


class StockfishEngine:
    """A Stockfish process that plays and evaluates one search at a time, restarting on failure.

    Attributes:
        name (str): The engine's name, as it reports it; `unknown` before `start`.
        build_tag (str | None): The release tag from the `VERSION` file, if it exists.
    """

    def __init__(self, path: str, threads: int, hash_mb: int, version_file: Path) -> None:
        """Creates the engine; the process starts with `start`.

        Args:
            path (str): The Stockfish binary.
            threads (int): The `Threads` option.
            hash_mb (int): The `Hash` option, in MB.
            version_file (Path): The image's `VERSION` file, read for the build tag if it exists.
        """
        self._path = path
        self._threads = threads
        self._hash_mb = hash_mb
        self._version_file = version_file
        self._engine: chess.engine.UciProtocol | None = None
        self._lock = asyncio.Lock()
        self.name = "unknown"
        self.build_tag: str | None = None

    async def start(self) -> None:
        """Starts Stockfish, configures it and reads its name and build tag."""
        _, self._engine = await chess.engine.popen_uci(self._path)
        await self._engine.configure({"Threads": self._threads, "Hash": self._hash_mb})
        self.name = self._engine.id.get("name", "unknown")
        if self._version_file.exists():
            self.build_tag = self._version_file.read_text(encoding="utf-8").strip()
        logger.info("engine started: %s (build %s)", self.name, self.build_tag)

    async def stop(self) -> None:
        """Asks Stockfish to quit, waiting up to 5 s; does nothing if it is not running."""
        if self._engine is not None:
            try:
                await asyncio.wait_for(self._engine.quit(), timeout=5)
            except (chess.engine.EngineError, TimeoutError):
                logger.warning("engine did not quit cleanly")
            self._engine = None

    async def play(
        self, board: chess.Board, level: Level, max_time_s: float | None = None
    ) -> chess.Move:
        """Chooses the bot's move at a level, restarting Stockfish once if it fails.

        Args:
            board (chess.Board): The position, with the bot to move.
            level (Level): The strength to play at.
            max_time_s (float | None): The most the search may take, from the bot's clock.

        Returns:
            chess.Move: The move.

        Raises:
            EngineUnavailableError: Stockfish failed again after the restart.
        """
        limit = limit_for(level, max_time_s)
        async with self._lock:
            try:
                return await self._search(board, level, limit)
            except (chess.engine.EngineError, EngineUnavailableError) as error:
                logger.warning("engine failed (%s), restarting", error)
            try:
                await self.stop()
                await self.start()
                return await self._search(board, level, limit)
            except (chess.engine.EngineError, OSError) as error:
                raise EngineUnavailableError(str(error)) from error

    async def evaluate(
        self, board: chess.Board, time_s: float
    ) -> tuple[chess.engine.PovScore, chess.Move | None]:
        """Evaluates a position at full strength: level options apply only while the bot plays.

        Args:
            board (chess.Board): The position.
            time_s (float): How long to search, in seconds.

        Returns:
            tuple[chess.engine.PovScore, chess.Move | None]: The score and the best move, if any.

        Raises:
            EngineUnavailableError: Stockfish failed again after a restart.
        """
        async with self._lock:
            try:
                return await self._analyse(board, time_s)
            except (chess.engine.EngineError, EngineUnavailableError) as error:
                logger.warning("engine failed (%s), restarting", error)
            try:
                await self.stop()
                await self.start()
                return await self._analyse(board, time_s)
            except (chess.engine.EngineError, OSError) as error:
                raise EngineUnavailableError(str(error)) from error

    async def _analyse(
        self, board: chess.Board, time_s: float
    ) -> tuple[chess.engine.PovScore, chess.Move | None]:
        """Runs one analysis, without the lock or the restart.

        Args:
            board (chess.Board): The position.
            time_s (float): How long to search, in seconds.

        Returns:
            tuple[chess.engine.PovScore, chess.Move | None]: The score and the first move of the PV.

        Raises:
            EngineUnavailableError: Stockfish is not running or returned no score.
        """
        if self._engine is None:
            raise EngineUnavailableError("engine is not running")
        info = await self._engine.analyse(board, chess.engine.Limit(time=time_s))
        score = info.get("score")
        if score is None:
            raise EngineUnavailableError("engine returned no score")
        pv = info.get("pv") or [None]
        return score, pv[0]

    async def _search(
        self, board: chess.Board, level: Level, limit: chess.engine.Limit
    ) -> chess.Move:
        """Runs one search with the level's options, without the lock or the restart.

        Args:
            board (chess.Board): The position.
            level (Level): The level whose options apply.
            limit (chess.engine.Limit): The search limit.

        Returns:
            chess.Move: The move found.

        Raises:
            EngineUnavailableError: Stockfish is not running or returned no move.
        """
        if self._engine is None:
            raise EngineUnavailableError("engine is not running")
        result = await self._engine.play(board, limit, options=level.options)
        if result.move is None:
            raise EngineUnavailableError("engine returned no move")
        return result.move
