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

import chess
import chess.pgn

from app.book.models import BookMove, Variant
from app.game.pace import TimeControl

Side = Literal["user", "bot"]
MoveSource = Literal["book", "engine"] | None

CHESS960_PREFIX = "chess960:"


class IllegalMoveError(ValueError):
    """The move is malformed or not legal in the position."""

    pass


class GameFinishedError(ValueError):
    """The game is over, so it takes no more moves, resignations or take-backs."""

    pass


class NotYourTurnError(ValueError):
    """The user tried to move while it is the bot's turn."""

    pass


class NothingToTakeBackError(ValueError):
    """There is no user move to take back, or the bot's reply was already shown."""

    pass


# Endings that come from a player, not from the position: a take-back cannot undo them.
DECIDED_BY_PLAYER = {"resignation", "timeout", "timeout_insufficient_material", "abandoned"}


def chess960_line(position: int) -> Variant:
    """A line with no theory: a Chess960 game is played against the engine from the first move.

    Args:
        position (int): The Chess960 starting position, 0 to 959.

    Returns:
        Variant: A line with no moves, whose id is `chess960:<position>`.
    """
    return Variant(
        variant_id=f"{CHESS960_PREFIX}{position}",
        repertoire_id="chess960",
        names={"en": "Chess960"},
        eco=None,
        opening=None,
        source=f"Chess960 position {position}",
        pgn="",
        moves={},
        positions=frozenset(),
        final_epd=chess.Board.from_chess960_pos(position).epd(),
    )


def chess960_position_of(fen: str) -> int | None:
    """The number of a Chess960 starting position, or None if the FEN is anything else.

    Args:
        fen (str): The FEN typed by the user.

    Returns:
        int | None: The position number, 0 to 959, or None.
    """
    try:
        return chess.Board(fen, chess960=True).chess960_pos()
    except ValueError:
        return None


class Selection:
    """The selected variations: their union is the theory for this game.

    Attributes:
        variants (list[Variant]): The selected lines.
    """

    def __init__(self, variants: Sequence[Variant]) -> None:
        """Creates the selection.

        Args:
            variants (Sequence[Variant]): The selected lines.
        """
        self.variants = list(variants)

    def moves_at(self, epd: str) -> dict[str, str]:
        """The theory moves from a position, over every selected line.

        Args:
            epd (str): The position.

        Returns:
            dict[str, str]: UCI -> SAN.
        """
        return {
            move.uci: move.san for variant in self.variants for move in variant.moves.get(epd, ())
        }

    def containing(self, epd: str) -> list[Variant]:
        """The selected lines that pass through a position.

        Args:
            epd (str): The position.

        Returns:
            list[Variant]: The lines, in selection order.
        """
        return [variant for variant in self.variants if epd in variant.positions]

    def has_position(self, epd: str) -> bool:
        """Whether any selected line passes through a position.

        Args:
            epd (str): The position.

        Returns:
            bool: True if one does.
        """
        return any(epd in variant.positions for variant in self.variants)


@dataclass(frozen=True, slots=True)
class MoveRecord:
    """One move of the game, as saved.

    Attributes:
        ply (int): The move's ply, from 1.
        san (str): The move in SAN.
        uci (str): The move in UCI.
        fen_before (str): The position before the move.
        by (Side): Who played it, `user` or `bot`.
        source (MoveSource): `book` or `engine` for a bot move, None for a user move.
        in_theory (bool): Whether the game was still in theory after it.
        clock_ms_after (int | None): The mover's clock after it, or None without a clock.
        think_ms (int | None): How long the move took, if known.
        opening (tuple[str, str] | None): (ECO, name) of the last named position reached.
    """

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
class BotDeviationSetup:
    """When the bot may leave its line on purpose (brief §6, bot deviation).

    Attributes:
        from_move (int): The first full-move number the bot rolls the die on.
        chance (int): The chance of deviating on each roll, in percent.
    """

    from_move: int
    chance: int


@dataclass(frozen=True, slots=True)
class Deviation:
    """A move that left theory where the selected lines had a move: the user's or the bot's.

    Attributes:
        ply (int): The move's ply.
        played_san (str): The move played.
        expected_san (tuple[str, ...]): The theory moves; for the bot, its line's move.
    """

    ply: int
    played_san: str
    expected_san: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GameResult:
    """How a game ended, from the user's side.

    Attributes:
        result (Literal["win", "draw", "loss"]): The result for the user.
        termination (str): Why it ended, such as `checkmate` or `resignation`.
    """

    result: Literal["win", "draw", "loss"]
    termination: str


def _pgn_termination(termination: str) -> str:
    """The PGN `Termination` tag for an ending.

    Args:
        termination (str): The ending, such as `timeout`.

    Returns:
        str: `Time forfeit`, `Abandoned` or `Normal`.
    """
    if termination.startswith("timeout"):
        return "Time forfeit"
    return "Abandoned" if termination == "abandoned" else "Normal"


def _pgn_time_control(control: TimeControl) -> str:
    """Standard PGN for periods and increment. Delay has no standard form: d or us, in seconds.

    Args:
        control (TimeControl): The time control.

    Returns:
        str: The `TimeControl` tag, such as `40/7200+30:1800+30`.
    """
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
    """One game in play: board, clocks, the line the bot follows, theory and deviations.

    Attributes:
        game_id (str): The game's id.
        selection (Selection): The selected lines.
        user_color (chess.Color): The user's color.
        time_control_key (str): The time control's key, such as `25i10`.
        time_control (TimeControl | None): The time control, or None without a clock.
        level (str): The bot's level key.
        pace (str): `instant` or `human`.
        rng (random.Random): The random source for the draw of lines and moves.
        chess960_position (int | None): The Chess960 starting position, or None.
        opening_names (Mapping[str, tuple[str, str]]): EPD -> (ECO, name); empty for Chess960.
        engine_name (str): The engine's name, for the PGN.
        ui (dict[str, bool]): UI flags saved with the game.
        user_clock_ms (int | None): The user's clock.
        bot_clock_ms (int | None): The bot's clock.
        board (chess.Board): The current position.
        started_at (datetime): When the game started, UTC.
        moves (list[MoveRecord]): The moves played.
        deviations (list[Deviation]): The user's deviations.
        bot_deviation_setup (BotDeviationSetup | None): When the bot may deviate, or None.
        bot_deviation (Deviation | None): The bot's deviation, once it deviated.
        in_theory (bool): Whether the game is still in theory.
        theory_until_ply (int): The last ply in theory.
        outcome (GameResult | None): How the game ended, or None while it runs.
        variant (Variant): The line the bot follows, drawn from the selection.
    """

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
        chess960_position: int | None = None,
    ) -> None:
        """Starts a game and draws the line the bot follows.

        Args:
            game_id (str): The game's id.
            selection (Selection): The selected lines; at least one.
            user_color (chess.Color): The user's color.
            time_control_key (str): The time control's key.
            time_control (TimeControl | None): The time control, or None without a clock.
            level (str): The bot's level key.
            pace (str): `instant` or `human`.
            rng (random.Random): The random source.
            opening_names (Mapping[str, tuple[str, str]] | None): EPD -> (ECO, name).
            engine_name (str): The engine's name, for the PGN.
            chess960_position (int | None): The Chess960 starting position, or None for chess.

        Raises:
            ValueError: The selection is empty.
        """
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
        self.chess960_position = chess960_position
        # Opening names and theory describe the normal starting position only.
        self.opening_names = (opening_names or {}) if chess960_position is None else {}
        self.engine_name = engine_name
        self.ui: dict[str, bool] = {}
        self.user_clock_ms: int | None = None
        self.bot_clock_ms: int | None = None
        self.board = (
            chess.Board()
            if chess960_position is None
            else chess.Board.from_chess960_pos(chess960_position)
        )
        self.started_at = datetime.now(UTC)
        self.moves: list[MoveRecord] = []
        self.deviations: list[Deviation] = []
        self.bot_deviation_setup: BotDeviationSetup | None = None
        self.bot_deviation: Deviation | None = None
        self.in_theory = chess960_position is None
        self.theory_until_ply = 0
        self.outcome: GameResult | None = None
        self.variant = rng.choice(selection.variants)

    @property
    def ply(self) -> int:
        """The number of plies played.

        Returns:
            int: The ply count.
        """
        return len(self.moves)

    @property
    def opening(self) -> tuple[str, str] | None:
        """(ECO, name) of the last named position reached in this game.

        Returns:
            tuple[str, str] | None: The opening, or None before any named position.
        """
        return self.moves[-1].opening if self.moves else None

    @property
    def is_over(self) -> bool:
        """Whether the game has ended.

        Returns:
            bool: True once there is an outcome.
        """
        return self.outcome is not None

    @property
    def is_user_turn(self) -> bool:
        """Whether the user is to move.

        Returns:
            bool: True on the user's turn.
        """
        return self.board.turn == self.user_color

    @property
    def left_theory_at_move(self) -> int | None:
        """Full-move number of the first ply out of theory, while the game is out of it.

        Returns:
            int | None: The move number, or None in theory and in Chess960.
        """
        if self.in_theory or self.chess960_position is not None:
            return None
        return (self.theory_until_ply + 2) // 2

    def play_user_move(
        self,
        uci: str,
        user_clock_ms: int | None = None,
        think_ms: int | None = None,
    ) -> tuple[MoveRecord, Deviation | None]:
        """Plays the user's move, recording a deviation if it leaves theory where theory had a move.

        Args:
            uci (str): The move in UCI.
            user_clock_ms (int | None): The user's clock after the move.
            think_ms (int | None): How long the move took.

        Returns:
            tuple[MoveRecord, Deviation | None]: The move and its deviation, if it was one.

        Raises:
            GameFinishedError: The game is over.
            NotYourTurnError: It is the bot's turn.
            IllegalMoveError: The move is malformed or illegal.
        """
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
        """Picks the bot's book move, redrawing the line if the user went into another one.

        Returns:
            BookMove | None: The move, or None when the engine has to take over.
        """
        if not self.in_theory:
            return None
        epd = self.board.epd()
        if epd not in self.variant.positions:
            self.variant = self.rng.choice(self.selection.containing(epd))
        moves = self.variant.moves.get(epd)
        return self.rng.choice(moves) if moves else None

    def rolls_for_deviation(self) -> bool:
        """Whether the bot rolls the die now: it is on, unused, in theory and from its move on.

        Call it only when the bot has a book move to play.

        Returns:
            bool: True if the bot rolls.
        """
        setup = self.bot_deviation_setup
        return (
            setup is not None
            and self.bot_deviation is None
            and self.in_theory
            and self.chess960_position is None
            and not self.is_user_turn
            and self.board.fullmove_number >= setup.from_move
        )

    def roll_deviation(self) -> bool:
        """Rolls the die for a bot deviation.

        Returns:
            bool: True on a hit, with the setup's chance.
        """
        setup = self.bot_deviation_setup
        return setup is not None and self.rng.randrange(100) < setup.chance

    def deviation_candidates(self, moves: Sequence[str]) -> list[str]:
        """The moves that would leave the selected lines from the current position.

        A move that transposes into a selected line stays in theory, so it is left out.

        Args:
            moves (Sequence[str]): Moves in UCI, legal in the current position.

        Returns:
            list[str]: The moves no selected line plays here and that reach none of their
                positions, in the given order.
        """
        selected = self.selection.moves_at(self.board.epd())
        return [uci for uci in moves if uci not in selected and not self._reaches_selection(uci)]

    def play_bot_deviation(
        self,
        move: chess.Move,
        source: Literal["book", "engine"],
        expected_san: str,
        bot_clock_ms: int | None = None,
        think_ms: int | None = None,
    ) -> MoveRecord:
        """Plays the bot's deviation: the game leaves theory and the deviation is recorded.

        Args:
            move (chess.Move): The move, outside the selected lines.
            source (Literal["book", "engine"]): Where it came from.
            expected_san (str): The move the bot's line had.
            bot_clock_ms (int | None): The bot's clock after the move.
            think_ms (int | None): How long the move took, delay included.

        Returns:
            MoveRecord: The move.

        Raises:
            GameFinishedError: The game is over.
        """
        if self.is_over:
            raise GameFinishedError(self.game_id)
        self.bot_deviation = Deviation(self.ply + 1, self.board.san(move), (expected_san,))
        self.in_theory = False
        return self._push(move, "bot", source, bot_clock_ms, think_ms)

    def play_bot_move(
        self,
        move: chess.Move,
        source: Literal["book", "engine"],
        bot_clock_ms: int | None = None,
        think_ms: int | None = None,
    ) -> MoveRecord:
        """Plays the bot's move.

        Args:
            move (chess.Move): The move.
            source (Literal["book", "engine"]): Where it came from.
            bot_clock_ms (int | None): The bot's clock after the move.
            think_ms (int | None): How long the move took, delay included.

        Returns:
            MoveRecord: The move.

        Raises:
            GameFinishedError: The game is over.
        """
        if self.is_over:
            raise GameFinishedError(self.game_id)
        if self.in_theory and not self._stays_in_theory(move):
            self.in_theory = False
        return self._push(move, "bot", source, bot_clock_ms, think_ms)

    def play_given_move(self, uci: str) -> None:
        """Plays a move that was already played in the game this one continues from.

        Args:
            uci (str): The move in UCI.
        """
        move = chess.Move.from_uci(uci)
        by: Side = "user" if self.is_user_turn else "bot"
        self._push(move, by, "book", None, None)

    def take_back(self, shown_plies: int) -> None:
        """Undoes the user's last move while the browser still has not shown the bot's reply.

        `shown_plies` counts the user's move. The bot's reply, already played here, goes too, and
        so does an end of the game that it caused. Theory and deviations go back to before.

        Args:
            shown_plies (int): The plies the browser shows, the user's move included.

        Raises:
            GameFinishedError: A player ended the game, or the browser already shows its end.
            NothingToTakeBackError: The last shown move is not the user's, or more was shown.
        """
        if self.outcome is not None and (
            self.outcome.termination in DECIDED_BY_PLAYER or self.ply <= shown_plies
        ):
            raise GameFinishedError(self.game_id)
        if (
            not 1 <= shown_plies <= self.ply
            or self.ply > shown_plies + 1
            or self.moves[shown_plies - 1].by != "user"
        ):
            raise NothingToTakeBackError(self.game_id)
        while self.ply >= shown_plies:
            self.moves.pop()
            self.board.pop()
        self.outcome = None
        self.deviations = [
            deviation for deviation in self.deviations if deviation.ply < shown_plies
        ]
        if self.bot_deviation is not None and self.bot_deviation.ply >= shown_plies:
            self.bot_deviation = None
        if self.chess960_position is None:
            self.in_theory = self.moves[-1].in_theory if self.moves else True
        self.theory_until_ply = max(
            (record.ply for record in self.moves if record.in_theory), default=0
        )

    def resign(self) -> None:
        """Ends the game as a loss by resignation.

        Raises:
            GameFinishedError: The game is already over.
        """
        if self.is_over:
            raise GameFinishedError(self.game_id)
        self.outcome = GameResult("loss", "resignation")

    def flag(self, side: Side, shown_plies: int) -> None:
        """A clock ran out. Drops moves the browser never showed: its clock is the authority.

        The game is a draw if the other side cannot mate.

        Args:
            side (Side): Whose clock ran out.
            shown_plies (int): The plies the browser shows.

        Raises:
            GameFinishedError: The game is already over.
        """
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
        """Whether a move is a theory move, or reaches a position of a selected line.

        Args:
            move (chess.Move): The move, not yet played.

        Returns:
            bool: True if the game stays in theory.
        """
        if move.uci() in self.selection.moves_at(self.board.epd()):
            return True
        return self._reaches_selection(move.uci())

    def _reaches_selection(self, uci: str) -> bool:
        """Whether a move reaches a position of a selected line.

        Args:
            uci (str): The move in UCI, not yet played.

        Returns:
            bool: True if a selected line passes through the position after it.
        """
        after = self.board.copy(stack=False)
        after.push_uci(uci)
        return self.selection.has_position(after.epd())

    def _push(
        self,
        move: chess.Move,
        by: Side,
        source: MoveSource,
        clock_ms_after: int | None,
        think_ms: int | None,
    ) -> MoveRecord:
        """Plays a move on the board, records it and checks for the end of the game.

        Args:
            move (chess.Move): The move.
            by (Side): Who played it.
            source (MoveSource): `book`, `engine` or None.
            clock_ms_after (int | None): The mover's clock after it.
            think_ms (int | None): How long it took.

        Returns:
            MoveRecord: The record.
        """
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
        """Sets the outcome if the position ends the game: repetition, fifty moves, mate..."""
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
        """(White, Black), as written in the PGN.

        Returns:
            tuple[str, str]: "You" and the bot's name with its level.
        """
        bot = f"{self.engine_name} ({self.level})"
        return ("You", bot) if self.user_color == chess.WHITE else (bot, "You")

    def result_tag(self) -> str:
        """The PGN `Result` tag.

        Returns:
            str: `1-0`, `0-1`, `1/2-1/2`, or `*` while the game runs.
        """
        if self.outcome is None:
            return "*"
        if self.outcome.result == "draw":
            return "1/2-1/2"
        user_won = self.outcome.result == "win"
        return "1-0" if user_won == (self.user_color == chess.WHITE) else "0-1"

    def pgn(self) -> str:
        """The game as PGN: tags, `[%clk]` on each move and both sides' deviations as comments.

        Returns:
            str: The PGN.
        """
        game = chess.pgn.Game()
        if self.chess960_position is not None:
            game.setup(chess.Board.from_chess960_pos(self.chess960_position))  # [FEN], [Variant]
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
        if self.chess960_position is None:
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
            bot = self.bot_deviation
            if bot is not None and bot.ply == record.ply:
                node.comment = f"Bot deviation: line expected {', '.join(bot.expected_san)}"
            if record.clock_ms_after is not None:
                node.set_clock(record.clock_ms_after / 1000)
        output = io.StringIO()
        print(game, file=output)
        return output.getvalue().strip()
