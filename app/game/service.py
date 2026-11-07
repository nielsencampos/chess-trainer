"""Coordinates sessions with the book, the engine and the store."""

import random
import secrets
import string
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import chess

from app.book.models import Book
from app.engine.levels import Level
from app.engine.process import MoveEngine
from app.game.imports import read_pgn_text
from app.game.pace import TIME_CONTROLS, clock_after_move, engine_budget_s, human_delay_ms
from app.game.session import Deviation, GameResult, GameSession, MoveRecord, Selection, Side
from app.game.store import GameStore, restore_session

MAX_GAMES_IN_MEMORY = 32
GAME_ID_ALPHABET = string.ascii_lowercase + string.digits


def new_game_id(now: datetime | None = None) -> str:
    """UTC timestamp to the microsecond, then a random part. Sorts by start time."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S%f")
    random_part = "".join(secrets.choice(GAME_ID_ALPHABET) for _ in range(24))
    return f"{stamp}-{random_part[:12]}-{random_part[12:]}"


class UnknownGameError(KeyError):
    pass


class InvalidSetupError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BotReply:
    record: MoveRecord
    delay_ms: int


class GameService:
    def __init__(
        self,
        book: Book,
        engine: MoveEngine,
        levels: dict[str, Level],
        store: GameStore,
        rng: random.Random | None = None,
        opening_names: Mapping[str, tuple[str, str]] | None = None,
    ) -> None:
        self.opening_names = opening_names or {}
        self.book = book
        self.engine = engine
        self.levels = levels
        self.store = store
        self.rng = rng or random.Random()
        self._games: OrderedDict[str, GameSession] = OrderedDict()

    def _remember(self, session: GameSession) -> None:
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
    ) -> tuple[GameSession, BotReply | None]:
        if not variant_ids:
            raise InvalidSetupError("select at least one variation")
        if level not in self.levels:
            raise InvalidSetupError(f"unknown level {level!r}")
        if time_control not in TIME_CONTROLS:
            raise InvalidSetupError(f"unknown time control {time_control!r}")
        variants = []
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
        )
        session.ui = dict(ui or {})
        if control is not None:
            session.user_clock_ms = control.base_ms
            session.bot_clock_ms = control.base_ms
        self._remember(session)
        self.store.save(session)

        reply = None if session.is_user_turn else await self._bot_turn(session)
        return session, reply

    def _abandon_active(self) -> None:
        """Only one game runs at a time. The app itself never starts a game over another."""
        session = self.active_session()
        if session is not None:
            session.outcome = GameResult("loss", "abandoned")
            self.store.save(session)

    def active_session(self) -> GameSession | None:
        row = self.store.active_row()
        if row is None:
            return None
        session = self._games.get(row["game_id"])
        if session is None:
            session = restore_session(row, self.book, self.opening_names, self.rng)
            if session is None:
                return None
            self._remember(session)
        return session

    async def resume_active(self) -> GameSession | None:
        """The unfinished game, after playing the bot's reply if the app closed before it."""
        session = self.active_session()
        if session is not None and not session.is_user_turn:
            await self._bot_turn(session)
        return session

    def get(self, game_id: str) -> GameSession:
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
        games, errors = read_pgn_text(text, self.opening_names)
        duplicates = self.store.save_imported(games, new_game_id)
        return {
            "imported": len(games) - duplicates,
            "duplicates": duplicates,
            "errors": [
                {"index": e.index, "label": e.label, "code": e.code, "detail": e.detail}
                for e in errors
            ],
        }

    def resign(self, game_id: str) -> GameSession:
        session = self.get(game_id)
        session.resign()
        self.store.save(session)
        return session

    def flag(self, game_id: str, side: Side, shown_plies: int) -> GameSession:
        session = self.get(game_id)
        session.flag(side, shown_plies)
        self.store.save(session)
        return session

    async def _bot_turn(self, session: GameSession) -> BotReply | None:
        bot_clock_ms = session.bot_clock_ms
        book_move = session.next_book_move()
        if book_move is not None:
            move = chess.Move.from_uci(book_move.uci)
        else:
            budget = engine_budget_s(session.time_control, bot_clock_ms)
            move = await self.engine.play(session.board, self.levels[session.level], budget)
            if session.is_over:  # the user's clock ran out during the search
                return None
        in_book = book_move is not None
        delay_ms = (
            human_delay_ms(session.time_control, bot_clock_ms, in_book, self.rng)
            if session.pace == "human"
            else 0
        )
        clock_after = None
        if session.time_control is not None and bot_clock_ms is not None:
            moves_made = sum(record.by == "bot" for record in session.moves) + 1
            clock_after = clock_after_move(session.time_control, bot_clock_ms, delay_ms, moves_made)
        record = session.play_bot_move(move, "book" if in_book else "engine", clock_after, delay_ms)
        session.bot_clock_ms = clock_after
        self.store.save(session)
        return BotReply(record, delay_ms)
