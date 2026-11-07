"""Coordinates sessions with the book and the engine. Games live in RAM until Phase 2."""

import random
import uuid
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

import chess

from app.book.models import Book
from app.engine.levels import Level
from app.engine.process import MoveEngine
from app.game.pace import TIME_CONTROLS, human_delay_ms
from app.game.session import Deviation, GameSession, MoveRecord, Selection, Side

MAX_GAMES_IN_MEMORY = 32


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
        rng: random.Random | None = None,
    ) -> None:
        self.book = book
        self.engine = engine
        self.levels = levels
        self.rng = rng or random.Random()
        self._games: OrderedDict[str, GameSession] = OrderedDict()

    async def create_game(
        self,
        color: str,
        variant_ids: Sequence[str],
        level: str,
        pace: str,
        time_control: str,
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

        session = GameSession(
            game_id=uuid.uuid4().hex,
            selection=Selection(variants),
            user_color=chess.WHITE if color == "white" else chess.BLACK,
            time_control_key=time_control,
            time_control=TIME_CONTROLS[time_control],
            level=level,
            pace=pace,
            rng=self.rng,
        )
        self._games[session.game_id] = session
        while len(self._games) > MAX_GAMES_IN_MEMORY:
            self._games.popitem(last=False)

        reply = None
        if not session.is_user_turn:
            base_ms = session.time_control.base_ms if session.time_control else None
            reply = await self._bot_turn(session, base_ms)
        return session, reply

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
        reply = None if session.is_over else await self._bot_turn(session, bot_clock_ms)
        return session, record, deviation, reply

    def resign(self, game_id: str) -> GameSession:
        session = self.get(game_id)
        session.resign()
        return session

    def flag(self, game_id: str, side: Side, shown_plies: int) -> GameSession:
        session = self.get(game_id)
        session.flag(side, shown_plies)
        return session

    async def _bot_turn(self, session: GameSession, bot_clock_ms: int | None) -> BotReply | None:
        book_move = session.next_book_move()
        if book_move is not None:
            move = chess.Move.from_uci(book_move.uci)
        else:
            move = await self.engine.play(session.board, self.levels[session.level])
            if session.is_over:  # the user's clock ran out during the search
                return None
        in_book = book_move is not None
        delay_ms = (
            human_delay_ms(session.time_control, bot_clock_ms, in_book, self.rng)
            if session.pace == "human"
            else 0
        )
        record = session.play_bot_move(
            move, "book" if in_book else "engine", bot_clock_ms, delay_ms
        )
        return BotReply(record, delay_ms)
