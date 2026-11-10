"""Coordinates sessions with the book, the engine and the store."""

import json
import random
import secrets
import string
import time
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import chess

from app.book.models import Book, Variant
from app.engine.levels import Level
from app.engine.process import MoveEngine
from app.game.imports import read_pgn_text
from app.game.pace import TIME_CONTROLS, clock_after_move, engine_budget_s, human_delay_ms
from app.game.session import (
    BotDeviationSetup,
    Deviation,
    GameResult,
    GameSession,
    MoveRecord,
    Selection,
    Side,
    chess960_line,
    chess960_position_of,
)
from app.game.store import GAME_LINE_PREFIX, GameStore, restore_session

MAX_GAMES_IN_MEMORY = 32
# How long each of the two searches that check an engine deviation may take, at most.
DEVIATION_SEARCH_S = 0.2
GAME_ID_ALPHABET = string.ascii_lowercase + string.digits


def new_game_id(now: datetime | None = None) -> str:
    """A new game id: UTC timestamp to the microsecond, then a random part. Sorts by start time.

    Args:
        now (datetime | None): The start time; now when None.

    Returns:
        str: An id such as `20261107131159012345-agjrbaghrbag-rkajgrjabgaa`.
    """
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S%f")
    random_part = "".join(secrets.choice(GAME_ID_ALPHABET) for _ in range(24))
    return f"{stamp}-{random_part[:12]}-{random_part[12:]}"


class UnknownGameError(KeyError):
    """No game with this id is in memory."""

    pass


class InvalidSetupError(ValueError):
    """The new game's setup is invalid, such as an unknown level or no lines."""

    pass


@dataclass(frozen=True, slots=True)
class FromGame:
    """A new game that starts from a saved one.

    Attributes:
        game_id (str): The saved game's id.
        upto_ply (int | None): How many of its plies to use; all when None.
        from_position (bool): True to play from that position against Stockfish, False to train
            its moves as a one-line book.
    """

    game_id: str
    upto_ply: int | None = None
    from_position: bool = False


@dataclass(frozen=True, slots=True)
class BotReply:
    """The bot's move and how long the browser waits before showing it.

    Attributes:
        record (MoveRecord): The move.
        delay_ms (int): The Human pace delay, 0 with Instant.
    """

    record: MoveRecord
    delay_ms: int


class GameService:
    """Starts, plays, resumes and saves games, one at a time, with the book, engine and store.

    Attributes:
        opening_names (Mapping[str, tuple[str, str]]): EPD -> (ECO, catalog name).
        book (Book): The book.
        engine (MoveEngine): The engine.
        levels (dict[str, Level]): The strength levels by key.
        store (GameStore): Where games are saved.
        rng (random.Random): The random source.
        deviation_max_loss_cp (int): How much worse than the best move an engine deviation may be.
    """

    def __init__(
        self,
        book: Book,
        engine: MoveEngine,
        levels: dict[str, Level],
        store: GameStore,
        rng: random.Random | None = None,
        opening_names: Mapping[str, tuple[str, str]] | None = None,
        deviation_max_loss_cp: int = 100,
    ) -> None:
        """Creates the service.

        Args:
            book (Book): The book.
            engine (MoveEngine): The engine.
            levels (dict[str, Level]): The strength levels by key.
            store (GameStore): Where games are saved.
            rng (random.Random | None): The random source; a new one when None.
            opening_names (Mapping[str, tuple[str, str]] | None): EPD -> (ECO, name).
            deviation_max_loss_cp (int): How much worse than the best move, in centipawns, an
                engine deviation may be.
        """
        self.opening_names = opening_names or {}
        self.deviation_max_loss_cp = deviation_max_loss_cp
        # Every active line's moves by position: the sidelines a bot deviation draws from.
        self._book_moves: dict[str, dict[str, str]] = {}
        for variant in book.variants.values():
            for epd, moves in variant.moves.items():
                for move in moves:
                    self._book_moves.setdefault(epd, {})[move.uci] = move.san
        self.book = book
        self.engine = engine
        self.levels = levels
        self.store = store
        self.rng = rng or random.Random()
        self._games: OrderedDict[str, GameSession] = OrderedDict()

    def _remember(self, session: GameSession) -> None:
        """Keeps a session in memory, dropping the oldest beyond `MAX_GAMES_IN_MEMORY`.

        Args:
            session (GameSession): The session.
        """
        self._games[session.game_id] = session
        while len(self._games) > MAX_GAMES_IN_MEMORY:
            self._games.popitem(last=False)

    async def create_game(
        self,
        color: str,
        variant_ids: Sequence[str],
        level: str,
        pace: str,
        time_control: str,
        ui: Mapping[str, bool] | None = None,
        from_game: FromGame | None = None,
        chess960_position: int | None = None,
        bot_deviation: BotDeviationSetup | None = None,
    ) -> tuple[GameSession, BotReply | None]:
        """Starts a new game, abandoning an active one, and plays the bot's first move if it starts.

        Args:
            color (str): The user's color, `white` or `black`.
            variant_ids (Sequence[str]): The selected lines; empty for Chess960 or a saved game.
            level (str): The bot's level key.
            pace (str): `instant` or `human`.
            time_control (str): The time control's key, or `none`.
            ui (Mapping[str, bool] | None): UI flags to save with the game.
            from_game (FromGame | None): The saved game to start from, if any.
            chess960_position (int | None): The Chess960 starting position, if any.
            bot_deviation (BotDeviationSetup | None): When the bot may deviate; None for never.

        Returns:
            tuple[GameSession, BotReply | None]: The game, and the bot's move if it plays first.

        Raises:
            InvalidSetupError: The setup is invalid.
        """
        if chess960_position is not None and (from_game is not None or variant_ids):
            raise InvalidSetupError("a Chess960 game has no opening lines")
        if chess960_position is None and from_game is None and not variant_ids:
            raise InvalidSetupError("select at least one variation")
        if level not in self.levels:
            raise InvalidSetupError(f"unknown level {level!r}")
        if time_control not in TIME_CONTROLS:
            raise InvalidSetupError(f"unknown time control {time_control!r}")
        variants = []
        if chess960_position is not None:
            variants.append(chess960_line(chess960_position))
        elif from_game is not None:
            variants.append(self._saved_game_line(from_game))
        else:
            for variant_id in dict.fromkeys(variant_ids):
                variant = self.book.variants.get(variant_id)
                if variant is None:
                    raise InvalidSetupError(f"unknown variation {variant_id!r}")
                variants.append(variant)

        self._abandon_active()
        control = TIME_CONTROLS[time_control]
        session = GameSession(
            game_id=new_game_id(),
            selection=Selection(variants),
            user_color=chess.WHITE if color == "white" else chess.BLACK,
            time_control_key=time_control,
            time_control=control,
            level=level,
            pace=pace,
            rng=self.rng,
            opening_names=self.opening_names,
            engine_name=self.engine.name,
            chess960_position=chess960_position,
        )
        session.ui = dict(ui or {})
        session.bot_deviation_setup = bot_deviation if chess960_position is None else None
        if from_game is not None and from_game.from_position:
            self._play_given_moves(session, variants[0])
        if control is not None:
            session.user_clock_ms = control.base_ms
            session.bot_clock_ms = control.base_ms
        self._remember(session)
        self.store.save(session)

        reply = None if session.is_user_turn else await self._bot_turn(session)
        return session, reply

    async def _deviation_move(
        self, session: GameSession, budget_s: float | None
    ) -> tuple[chess.Move, Literal["book", "engine"]] | None:
        """Chooses the bot's deviation: a sideline of the book, else a sound engine move.

        Args:
            session (GameSession): The game, with the bot to move in theory.
            budget_s (float | None): The most the bot's clock allows a search, or None.

        Returns:
            tuple[chess.Move, Literal["book", "engine"]] | None: The move and where it came
                from, or None when no move qualifies.
        """
        board = session.board
        sidelines = session.deviation_candidates(list(self._book_moves.get(board.epd(), {})))
        if sidelines:
            return chess.Move.from_uci(self.rng.choice(sidelines)), "book"
        allowed = session.deviation_candidates([move.uci() for move in board.legal_moves])
        if not allowed:
            return None
        search_s = DEVIATION_SEARCH_S if budget_s is None else min(DEVIATION_SEARCH_S, budget_s / 2)
        best, _ = await self.engine.evaluate(board, search_s)
        score, move = await self.engine.evaluate(
            board, search_s, [chess.Move.from_uci(uci) for uci in allowed]
        )
        if move is None or move.uci() not in allowed:
            return None
        loss = best.pov(board.turn).score(mate_score=100_000) - score.pov(board.turn).score(
            mate_score=100_000
        )
        return (move, "engine") if loss <= self.deviation_max_loss_cp else None

    def _saved_game_line(self, from_game: FromGame) -> Variant:
        """A finished game's first plies as a one-line book.

        Args:
            from_game (FromGame): The saved game and how many plies to use.

        Returns:
            Variant: The line.

        Raises:
            InvalidSetupError: The game is unknown, unfinished or Chess960, or the ply is out of
                range.
        """
        game = self.store.finished_game(from_game.game_id)
        if game is None:
            raise InvalidSetupError("not a finished game")
        if game["chess960"]:
            raise InvalidSetupError("playing from a Chess960 game is not supported yet")
        total = len(json.loads(game["moves_json"]))
        plies = from_game.upto_ply or total
        if not 1 <= plies <= total:
            raise InvalidSetupError(f"the game has {total} plies, not {plies}")
        line = self.store.game_line(f"{GAME_LINE_PREFIX}{from_game.game_id}:{plies}")
        if line is None:
            raise InvalidSetupError("this game cannot be played from")
        return line

    def chess960_start(self, fen: str | None) -> tuple[int, str]:
        """(number, FEN) of a starting position: the given FEN if there is one, or a random one.

        Args:
            fen (str | None): A typed FEN, or None to roll one.

        Returns:
            tuple[int, str]: The position number and its FEN.

        Raises:
            InvalidSetupError: The FEN is not a Chess960 starting position.
        """
        position = self.rng.randrange(960) if fen is None else chess960_position_of(fen)
        if position is None:
            raise InvalidSetupError("not a Chess960 starting position")
        return position, chess.Board.from_chess960_pos(position).fen()

    @staticmethod
    def _play_given_moves(session: GameSession, line: Variant) -> None:
        """Plays a line's moves on a new game, to start from the position they reach.

        Args:
            session (GameSession): The new game.
            line (Variant): The line.

        Raises:
            InvalidSetupError: The position is already the end of the game.
        """
        board = chess.Board()
        for _ in range(len(line.pgn.split())):
            uci = line.moves[board.epd()][0].uci
            session.play_given_move(uci)
            board.push_uci(uci)
        if session.is_over:
            raise InvalidSetupError("the game is already over at this move")

    def _abandon_active(self) -> None:
        """Ends the active game as abandoned, if any: only one game runs at a time."""
        session = self.active_session()
        if session is not None:
            session.outcome = GameResult("loss", "abandoned")
            self.store.save(session)

    def active_session(self) -> GameSession | None:
        """The unfinished game, from memory or rebuilt from the database.

        Returns:
            GameSession | None: The game, or None if there is none or its lines no longer exist.
        """
        row = self.store.active_row()
        if row is None:
            return None
        session = self._games.get(row["game_id"])
        if session is None:
            session = restore_session(row, self.book, self.opening_names, self.rng, self.store)
            if session is None:
                return None
            self._remember(session)
        return session

    async def resume_active(self) -> GameSession | None:
        """The unfinished game, after playing the bot's reply if the app closed before it.

        Returns:
            GameSession | None: The game, or None if there is none.
        """
        session = self.active_session()
        if session is not None and not session.is_user_turn:
            await self._bot_turn(session)
        return session

    def get(self, game_id: str) -> GameSession:
        """A game in memory.

        Args:
            game_id (str): The game's id.

        Returns:
            GameSession: The game.

        Raises:
            UnknownGameError: The game is not in memory.
        """
        try:
            return self._games[game_id]
        except KeyError as error:
            raise UnknownGameError(game_id) from error

    async def user_move(
        self,
        game_id: str,
        uci: str,
        user_clock_ms: int | None,
        bot_clock_ms: int | None,
        think_ms: int | None,
    ) -> tuple[GameSession, MoveRecord, Deviation | None, BotReply | None]:
        """Plays the user's move, saves it, then plays and saves the bot's reply.

        Args:
            game_id (str): The game's id.
            uci (str): The move in UCI.
            user_clock_ms (int | None): The user's clock after the move, from the browser.
            bot_clock_ms (int | None): The bot's clock, from the browser.
            think_ms (int | None): How long the user's move took.

        Returns:
            tuple[GameSession, MoveRecord, Deviation | None, BotReply | None]: The game, the user's
                move, its deviation if it was one, and the bot's reply unless the game ended.

        Raises:
            UnknownGameError: The game is not in memory.
            IllegalMoveError: The move is illegal.
        """
        session = self.get(game_id)
        record, deviation = session.play_user_move(uci, user_clock_ms, think_ms)
        if user_clock_ms is not None:
            session.user_clock_ms = user_clock_ms
        if bot_clock_ms is not None:
            session.bot_clock_ms = bot_clock_ms
        self.store.save(session)
        reply = None if session.is_over else await self._bot_turn(session)
        return session, record, deviation, reply

    def import_pgn(self, text: str) -> dict:
        """Imports the games of a PGN text, skipping or updating duplicates.

        Args:
            text (str): One or more PGN games.

        Returns:
            dict: Counts of `imported`, `duplicates` and `updated`, and the refused games in
                `errors`.
        """
        games, errors = read_pgn_text(text, self.opening_names)
        duplicates, updated = self.store.save_imported(games, new_game_id)
        return {
            "imported": len(games) - duplicates - updated,
            "duplicates": duplicates,
            "updated": updated,
            "errors": [
                {"index": e.index, "label": e.label, "code": e.code, "detail": e.detail}
                for e in errors
            ],
        }

    def resign(self, game_id: str) -> GameSession:
        """Resigns a game and saves it.

        Args:
            game_id (str): The game's id.

        Returns:
            GameSession: The game.

        Raises:
            UnknownGameError: The game is not in memory.
            GameFinishedError: The game is already over.
        """
        session = self.get(game_id)
        session.resign()
        self.store.save(session)
        return session

    def take_back(
        self,
        game_id: str,
        shown_plies: int,
        user_clock_ms: int | None,
        bot_clock_ms: int | None,
    ) -> GameSession:
        """Takes back the user's last move; the clocks come back as they were before it.

        Args:
            game_id (str): The game's id.
            shown_plies (int): The plies the browser shows, the user's move included.
            user_clock_ms (int | None): The user's clock before the move.
            bot_clock_ms (int | None): The bot's clock before the move.

        Returns:
            GameSession: The game.

        Raises:
            UnknownGameError: The game is not in memory.
            GameFinishedError: The game's end cannot be undone.
            NothingToTakeBackError: There is no move to take back.
        """
        session = self.get(game_id)
        session.take_back(shown_plies)
        if user_clock_ms is not None:
            session.user_clock_ms = user_clock_ms
        if bot_clock_ms is not None:
            session.bot_clock_ms = bot_clock_ms
        self.store.save(session)
        return session

    def flag(self, game_id: str, side: Side, shown_plies: int) -> GameSession:
        """Ends a game on time and saves it.

        Args:
            game_id (str): The game's id.
            side (Side): Whose clock ran out.
            shown_plies (int): The plies the browser shows.

        Returns:
            GameSession: The game.

        Raises:
            UnknownGameError: The game is not in memory.
            GameFinishedError: The game is already over.
        """
        session = self.get(game_id)
        session.flag(side, shown_plies)
        self.store.save(session)
        return session

    async def _bot_turn(self, session: GameSession) -> BotReply | None:
        """Plays the bot's move, from the book or the engine, and charges its clock.

        Args:
            session (GameSession): The game, with the bot to move.

        Returns:
            BotReply | None: The move, or None if the game ended during the search.
        """
        bot_clock_ms = session.bot_clock_ms
        book_move = session.next_book_move()
        search_started = time.monotonic()
        budget = engine_budget_s(session.time_control, bot_clock_ms)
        deviation = None
        if book_move is not None and session.rolls_for_deviation() and session.roll_deviation():
            deviation = await self._deviation_move(session, budget)
            if session.is_over:  # the user's clock ran out during the search
                return None
        if deviation is not None:
            move, source = deviation
        elif book_move is not None:
            move, source = chess.Move.from_uci(book_move.uci), "book"
        else:
            move = await self.engine.play(session.board, self.levels[session.level], budget)
            source = "engine"
            if session.is_over:  # the user's clock ran out during the search
                return None
        in_book = source == "book"
        delay_ms = (
            human_delay_ms(session.time_control, bot_clock_ms, in_book, self.rng)
            if session.pace == "human"
            else 0
        )
        # Like the clock on screen, which runs from the user's move until the bot's move is shown:
        # the search happens inside the delay, and only a longer search adds to it.
        search_ms = int((time.monotonic() - search_started) * 1000)
        used_ms = max(delay_ms, search_ms)
        clock_after = None
        if session.time_control is not None and bot_clock_ms is not None:
            moves_made = sum(record.by == "bot" for record in session.moves) + 1
            clock_after = clock_after_move(session.time_control, bot_clock_ms, used_ms, moves_made)
        if deviation is not None and book_move is not None:
            record = session.play_bot_deviation(move, source, book_move.san, clock_after, used_ms)
        else:
            record = session.play_bot_move(move, source, clock_after, used_ms)
        session.bot_clock_ms = clock_after
        self.store.save(session)
        return BotReply(record, delay_ms)
