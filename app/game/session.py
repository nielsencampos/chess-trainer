"""State of one game: which line the bot follows, what counts as theory, how it ended.

The rules live in brief §6 ("Selection and draw"). Positions are compared by EPD, so a move
order that transposes back into a selected line is still theory.
"""

import io
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote

import chess
import chess.pgn

from app.book.models import BookMove, Variant
from app.game.pace import TimeControl

Side = Literal["user", "bot"]
MoveSource = Literal["book", "engine"] | None


class IllegalMoveError(ValueError):
    pass


class GameFinishedError(ValueError):
    pass


class NotYourTurnError(ValueError):
    pass


class Selection:
    """The selected variations: their union is the theory for this game."""

    def __init__(self, variants: Sequence[Variant]) -> None:
        self.variants = list(variants)

    def moves_at(self, epd: str) -> dict[str, str]:
        return {
            move.uci: move.san for variant in self.variants for move in variant.moves.get(epd, ())
        }

    def containing(self, epd: str) -> list[Variant]:
        return [variant for variant in self.variants if epd in variant.positions]

    def has_position(self, epd: str) -> bool:
        return any(epd in variant.positions for variant in self.variants)


@dataclass(frozen=True, slots=True)
class MoveRecord:
    ply: int
    san: str
    uci: str
    fen_before: str
    by: Side
    source: MoveSource
    in_theory: bool
    clock_ms_after: int | None
    think_ms: int | None
    opening: tuple[str, str] | None = None


@dataclass(frozen=True, slots=True)
class Deviation:
    ply: int
    played_san: str
    expected_san: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GameResult:
    result: Literal["win", "draw", "loss"]
    termination: str


def _pgn_termination(termination: str) -> str:
    if termination.startswith("timeout"):
        return "Time forfeit"
    return "Abandoned" if termination == "abandoned" else "Normal"


def _pgn_time_control(control: TimeControl) -> str:
    """Standard PGN for periods and increment. Delay has no standard form: d or us, in seconds."""
    suffix = f"+{control.increment_ms // 1000}"
    if control.delay_kind is not None:
        marker = "us" if control.delay_kind == "us" else "d"
        suffix = f"{marker}{control.delay_ms // 1000}"
    parts = []
    seconds = control.base_ms // 1000
    played = 0
    for period in control.periods:
        parts.append(f"{period.after_moves - played}/{seconds}{suffix}")
        played = period.after_moves
        seconds = period.add_ms // 1000
    parts.append(f"{seconds}{suffix}")
    return ":".join(parts)


class GameSession:
    def __init__(
        self,
        game_id: str,
        selection: Selection,
        user_color: chess.Color,
        time_control_key: str,
        time_control: TimeControl | None,
        level: str,
        pace: str,
        rng: random.Random,
        opening_names: Mapping[str, tuple[str, str]] | None = None,
        engine_name: str = "Bot",
    ) -> None:
        if not selection.variants:
            raise ValueError("a game needs at least one selected variation")
        self.game_id = game_id
        self.selection = selection
        self.user_color = user_color
        self.time_control_key = time_control_key
        self.time_control = time_control
        self.level = level
        self.pace = pace
        self.rng = rng
        self.opening_names = opening_names or {}
        self.engine_name = engine_name
        self.ui: dict[str, bool] = {}
        self.user_clock_ms: int | None = None
        self.bot_clock_ms: int | None = None
        self.board = chess.Board()
        self.started_at = datetime.now(UTC)
        self.moves: list[MoveRecord] = []
        self.deviations: list[Deviation] = []
        self.in_theory = True
        self.theory_until_ply = 0
        self.outcome: GameResult | None = None
        self.variant = rng.choice(selection.variants)

    @property
    def ply(self) -> int:
        return len(self.moves)

    @property
    def opening(self) -> tuple[str, str] | None:
        """(ECO, name) of the last named position reached in this game."""
        return self.moves[-1].opening if self.moves else None

    @property
    def is_over(self) -> bool:
        return self.outcome is not None

    @property
    def is_user_turn(self) -> bool:
        return self.board.turn == self.user_color

    @property
    def left_theory_at_move(self) -> int | None:
        """Full-move number of the first ply out of theory, while the game is out of it."""
        return None if self.in_theory else (self.theory_until_ply + 2) // 2

    def play_user_move(
        self,
        uci: str,
        user_clock_ms: int | None = None,
        think_ms: int | None = None,
    ) -> tuple[MoveRecord, Deviation | None]:
        if self.is_over:
            raise GameFinishedError(self.game_id)
        if not self.is_user_turn:
            raise NotYourTurnError(self.game_id)
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as error:
            raise IllegalMoveError(uci) from error
        if move not in self.board.legal_moves:
            raise IllegalMoveError(uci)

        deviation = None
        if self.in_theory:
            expected = self.selection.moves_at(self.board.epd())
            if not self._stays_in_theory(move):
                self.in_theory = False
                if expected:
                    deviation = Deviation(
                        self.ply + 1, self.board.san(move), tuple(expected.values())
                    )
                    self.deviations.append(deviation)
        record = self._push(move, "user", None, user_clock_ms, think_ms)
        return record, deviation

    def next_book_move(self) -> BookMove | None:
        """Pick the bot's book move, or None when the engine has to take over."""
        if not self.in_theory:
            return None
        epd = self.board.epd()
        if epd not in self.variant.positions:
            self.variant = self.rng.choice(self.selection.containing(epd))
        moves = self.variant.moves.get(epd)
        return self.rng.choice(moves) if moves else None

    def play_bot_move(
        self,
        move: chess.Move,
        source: Literal["book", "engine"],
        bot_clock_ms: int | None = None,
        think_ms: int | None = None,
    ) -> MoveRecord:
        if self.is_over:
            raise GameFinishedError(self.game_id)
        if self.in_theory and not self._stays_in_theory(move):
            self.in_theory = False
        return self._push(move, "bot", source, bot_clock_ms, think_ms)

    def play_given_move(self, uci: str) -> None:
        """A move that was already played in the game this one continues from."""
        move = chess.Move.from_uci(uci)
        by: Side = "user" if self.is_user_turn else "bot"
        self._push(move, by, "book", None, None)

    def resign(self) -> None:
        if self.is_over:
            raise GameFinishedError(self.game_id)
        self.outcome = GameResult("loss", "resignation")

    def flag(self, side: Side, shown_plies: int) -> None:
        """A clock ran out. Drops moves the browser never showed: its clock is the authority."""
        if self.is_over:
            raise GameFinishedError(self.game_id)
        while self.ply > shown_plies:
            self.moves.pop()
            self.board.pop()
        loser_color = self.user_color if side == "user" else not self.user_color
        if self.board.has_insufficient_material(not loser_color):
            self.outcome = GameResult("draw", "timeout_insufficient_material")
        else:
            self.outcome = GameResult("loss" if side == "user" else "win", "timeout")

    def _stays_in_theory(self, move: chess.Move) -> bool:
        if move.uci() in self.selection.moves_at(self.board.epd()):
            return True
        after = self.board.copy(stack=False)
        after.push(move)
        return self.selection.has_position(after.epd())

    def _push(
        self,
        move: chess.Move,
        by: Side,
        source: MoveSource,
        clock_ms_after: int | None,
        think_ms: int | None,
    ) -> MoveRecord:
        ply = self.ply + 1
        san = self.board.san(move)
        fen_before = self.board.fen()
        self.board.push(move)
        record = MoveRecord(
            ply=ply,
            san=san,
            uci=move.uci(),
            fen_before=fen_before,
            by=by,
            source=source,
            in_theory=self.in_theory,
            clock_ms_after=clock_ms_after,
            think_ms=think_ms,
            opening=self.opening_names.get(self.board.epd(), self.opening),
        )
        self.moves.append(record)
        if self.in_theory:
            self.theory_until_ply = record.ply
        self._check_game_over()
        return record

    def _check_game_over(self) -> None:
        # Not outcome(claim_draw=True): that also ends the game one move before the repetition.
        if self.board.is_repetition(3):
            self.outcome = GameResult("draw", "threefold_repetition")
            return
        if self.board.is_fifty_moves():
            self.outcome = GameResult("draw", "fifty_moves")
            return
        outcome = self.board.outcome()
        if outcome is None:
            return
        if outcome.winner is None:
            result = "draw"
        else:
            result = "win" if outcome.winner == self.user_color else "loss"
        self.outcome = GameResult(result, outcome.termination.name.lower())

    def players(self) -> tuple[str, str]:
        """(White, Black), as written in the PGN."""
        bot = f"{self.engine_name} ({self.level})"
        return ("You", bot) if self.user_color == chess.WHITE else (bot, "You")

    def result_tag(self) -> str:
        if self.outcome is None:
            return "*"
        if self.outcome.result == "draw":
            return "1/2-1/2"
        user_won = self.outcome.result == "win"
        return "1-0" if user_won == (self.user_color == chess.WHITE) else "0-1"

    def pgn(self) -> str:
        game = chess.pgn.Game()
        game.headers["Event"] = "chess-trainer"
        game.headers["Site"] = "local"
        game.headers["Date"] = self.started_at.strftime("%Y.%m.%d")
        game.headers["White"], game.headers["Black"] = self.players()
        game.headers["Result"] = self.result_tag()
        eco, opening = self.opening or (self.variant.eco, self.variant.opening)
        if eco:
            game.headers["ECO"] = eco
        if opening:
            game.headers["Opening"] = opening
        game.headers["VariantId"] = self.variant.variant_id
        if self.outcome is not None:
            game.headers["Termination"] = _pgn_termination(self.outcome.termination)
        if self.time_control is not None:
            game.headers["TimeControl"] = _pgn_time_control(self.time_control)
        node: chess.pgn.GameNode = game
        deviations = {deviation.ply: deviation for deviation in self.deviations}
        for record in self.moves:
            node = node.add_variation(chess.Move.from_uci(record.uci))
            deviation = deviations.get(record.ply)
            if deviation is not None:
                node.comment = f"Deviation: expected {', '.join(deviation.expected_san)}"
            if record.clock_ms_after is not None:
                node.set_clock(record.clock_ms_after / 1000)
        output = io.StringIO()
        print(game, file=output)
        return output.getvalue().strip()

    def lichess_url(self) -> str:
        sans = "_".join(record.san.rstrip("+#") for record in self.moves)
        color = "white" if self.user_color == chess.WHITE else "black"
        return f"https://lichess.org/analysis/pgn/{quote(sans, safe='_-')}?color={color}"
