"""State of one game: which line the bot follows, what counts as theory, how it ended.

The rules live in brief §6 ("Selection and draw"). Positions are compared by EPD, so a move
order that transposes back into a selected line is still theory.
"""

import io
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote

import chess
import chess.pgn

from app.book.loader import BookMove, Variant
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


@dataclass(frozen=True, slots=True)
class Deviation:
    ply: int
    played_san: str
    expected_san: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GameResult:
    result: Literal["win", "draw", "loss"]
    termination: str


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
        record = MoveRecord(
            ply=self.ply + 1,
            san=self.board.san(move),
            uci=move.uci(),
            fen_before=self.board.fen(),
            by=by,
            source=source,
            in_theory=self.in_theory,
            clock_ms_after=clock_ms_after,
            think_ms=think_ms,
        )
        self.board.push(move)
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
        game.headers["White"] = "You" if self.user_color == chess.WHITE else "Bot"
        game.headers["Black"] = "You" if self.user_color == chess.BLACK else "Bot"
        game.headers["Result"] = self.result_tag()
        if self.variant.eco:
            game.headers["ECO"] = self.variant.eco
        if self.variant.opening:
            game.headers["Opening"] = self.variant.opening
        if self.time_control is not None:
            base_s = self.time_control.base_ms // 1000
            game.headers["TimeControl"] = f"{base_s}+{self.time_control.increment_ms // 1000}"
        node: chess.pgn.GameNode = game
        for record in self.moves:
            node = node.add_variation(chess.Move.from_uci(record.uci))
        output = io.StringIO()
        print(game, file=output)
        return output.getvalue().strip()

    def lichess_url(self) -> str:
        sans = "_".join(record.san.rstrip("+#") for record in self.moves)
        color = "white" if self.user_color == chess.WHITE else "black"
        return f"https://lichess.org/analysis/pgn/{quote(sans, safe='_-')}?color={color}"
