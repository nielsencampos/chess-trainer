"""Request and response bodies of the HTTP API."""

from typing import Literal

import chess
from pydantic import BaseModel, Field

from app.game.service import BotReply
from app.game.session import Deviation, GameSession


class FromGameRequest(BaseModel):
    """A new game from a saved one.

    Attributes:
        game_id (str): The saved game.
        upto_ply (int | None): How many of its plies to use; all when None.
        mode (Literal["line", "position"]): Train its moves as a line, or play from the position.
    """

    game_id: str
    upto_ply: int | None = Field(default=None, ge=1)
    mode: Literal["line", "position"] = "line"


class BotDeviationRequest(BaseModel):
    """When the bot may leave its line on purpose (brief §6, bot deviation).

    Attributes:
        from_move (Literal[3, 4, 5, 6, 7]): The first full-move number the bot rolls the die on.
        chance (Literal[20, 30, 40, 50, 60, 70]): The chance of deviating on each roll, in percent.
    """

    from_move: Literal[3, 4, 5, 6, 7] = 3
    chance: Literal[20, 30, 40, 50, 60, 70] = 30


class NewGameRequest(BaseModel):
    """Body of `POST /api/games`.

    Attributes:
        color (Literal["white", "black"]): The user's color.
        variant_ids (list[str]): The selected lines; empty for Chess960 or a saved game.
        from_game (FromGameRequest | None): The saved game to start from, if any.
        chess960_position (int | None): The Chess960 starting position, if any.
        level (str): The bot's level key.
        pace (Literal["instant", "human"]): The bot's response time.
        time_control (str): The time control's key, or `none`.
        ui (dict[str, bool]): UI flags saved with the game.
        bot_deviation (BotDeviationRequest | None): When the bot may deviate; None for never.
    """

    color: Literal["white", "black"]
    variant_ids: list[str] = Field(default_factory=list)
    from_game: FromGameRequest | None = None
    chess960_position: int | None = Field(default=None, ge=0, le=959)
    level: str
    pace: Literal["instant", "human"]
    time_control: str
    ui: dict[str, bool] = Field(default_factory=dict)
    bot_deviation: BotDeviationRequest | None = None


class Chess960Request(BaseModel):
    """Body of `POST /api/chess960`. With no FEN, the server rolls the dice.

    Attributes:
        fen (str | None): A typed starting position, or None.
    """

    fen: str | None = Field(default=None, max_length=100)


class Chess960Start(BaseModel):
    """A Chess960 starting position.

    Attributes:
        position (int): Its number, 0 to 959.
        fen (str): Its FEN.
    """

    position: int
    fen: str


class MoveRequest(BaseModel):
    """Body of `POST /api/games/{game_id}/moves`.

    Attributes:
        uci (str): The user's move in UCI.
        user_clock_ms (int | None): The user's clock after the move, from the browser.
        bot_clock_ms (int | None): The bot's clock, from the browser.
        think_ms (int | None): How long the move took.
    """

    uci: str = Field(min_length=4, max_length=5)
    user_clock_ms: int | None = Field(default=None, ge=0)
    bot_clock_ms: int | None = Field(default=None, ge=0)
    think_ms: int | None = Field(default=None, ge=0)


class ImportRequest(BaseModel):
    """Body of `POST /api/games/import`.

    Attributes:
        pgn (str): One or more PGN games.
    """

    pgn: str = Field(max_length=50_000_000)


class RemoteImportRequest(BaseModel):
    """Body of `POST /api/games/import/remote`.

    Attributes:
        site (Literal["lichess", "chesscom"]): Where to fetch from.
        username (str): The player's username.
        months (int): The period, 1 to 12 months.
    """

    site: Literal["lichess", "chesscom"]
    username: str = Field(min_length=1, max_length=30)
    months: int = Field(ge=1, le=12)


class ExportRequest(BaseModel):
    """Body of `POST /api/games/export`.

    Attributes:
        game_ids (list[str]): The games to export.
    """

    game_ids: list[str] = Field(min_length=1)


class DeleteRequest(BaseModel):
    """Body of `POST /api/games/delete`.

    Attributes:
        game_ids (list[str]): The games to delete.
    """

    game_ids: list[str] = Field(min_length=1)


class ExportLinesRequest(BaseModel):
    """Body of `POST /api/lines/export`.

    Attributes:
        variant_ids (list[str]): The lines to export.
    """

    variant_ids: list[str] = Field(min_length=1)


class EvaluateRequest(BaseModel):
    """A position the app itself produced: the board on screen, never a user's FEN.

    Attributes:
        fen (str): The position.
        chess960 (bool): Whether it is a Chess960 game, for castling.
    """

    fen: str = Field(max_length=100)
    chess960: bool = False


class EvaluationOut(BaseModel):
    """An evaluation from White's side.

    Attributes:
        cp (int | None): Centipawns, or None when there is a mate.
        mate (int | None): Moves to mate, negative when Black mates, or None.
        best (str | None): The best move in UCI, if any.
    """

    cp: int | None
    mate: int | None
    best: str | None


class TakeBackRequest(BaseModel):
    """Body of `POST /api/games/{game_id}/takeback`.

    Attributes:
        shown_plies (int): The plies the browser shows, the user's move included.
        user_clock_ms (int | None): The user's clock before the move.
        bot_clock_ms (int | None): The bot's clock before the move.
    """

    shown_plies: int = Field(ge=1)
    user_clock_ms: int | None = Field(default=None, ge=0)
    bot_clock_ms: int | None = Field(default=None, ge=0)


class FlagRequest(BaseModel):
    """Body of `POST /api/games/{game_id}/timeout`.

    Attributes:
        side (Literal["user", "bot"]): Whose clock ran out.
        shown_plies (int): The plies the browser shows.
    """

    side: Literal["user", "bot"]
    shown_plies: int = Field(ge=0)


class OpeningOut(BaseModel):
    """A named position.

    Attributes:
        eco (str): The ECO code.
        name (str): The catalog name, in English.
    """

    eco: str
    name: str


class BotMoveOut(BaseModel):
    """The bot's move.

    Attributes:
        opening (OpeningOut | None): The last named position reached.
        uci (str): The move in UCI.
        san (str): The move in SAN.
        ply (int): Its ply.
        source (Literal["book", "engine"]): Where it came from.
        delay_ms (int): How long the browser waits before showing it.
        in_theory (bool): Whether the game is still in theory after it.
    """

    opening: OpeningOut | None = None
    uci: str
    san: str
    ply: int
    source: Literal["book", "engine"]
    delay_ms: int
    in_theory: bool


class DeviationOut(BaseModel):
    """A user deviation.

    Attributes:
        ply (int): The move's ply.
        move_number (int): Its full-move number.
        played_san (str): The move played.
        expected_san (list[str]): The theory moves.
    """

    ply: int
    move_number: int
    played_san: str
    expected_san: list[str]


class GameStateOut(BaseModel):
    """The state of a game after a request.

    Attributes:
        opening (OpeningOut | None): The last named position reached.
        game_id (str): The game's id.
        fen (str): The current position.
        ply (int): The plies played.
        in_theory (bool): Whether the game is in theory.
        theory_until_ply (int): The last ply in theory.
        left_theory_at_move (int | None): The move it left theory at, if it did.
        game_over (bool): Whether the game has ended.
        bot_deviation (DeviationOut | None): The bot's deviation, once it deviated.
    """

    opening: OpeningOut | None = None
    game_id: str
    fen: str
    ply: int
    in_theory: bool
    theory_until_ply: int
    left_theory_at_move: int | None
    game_over: bool
    bot_deviation: DeviationOut | None = None


class NewGameResponse(BaseModel):
    """Response of `POST /api/games`.

    Attributes:
        state (GameStateOut): The new game.
        bot_move (BotMoveOut | None): The bot's first move, when the user plays Black.
    """

    state: GameStateOut
    bot_move: BotMoveOut | None


class UserMoveOut(BaseModel):
    """The user's move, as the server recorded it.

    Attributes:
        opening (OpeningOut | None): The last named position reached.
        uci (str): The move in UCI.
        san (str): The move in SAN.
        ply (int): Its ply.
        in_theory (bool): Whether the game is still in theory after it.
    """

    opening: OpeningOut | None = None
    uci: str
    san: str
    ply: int
    in_theory: bool


class MoveResponse(BaseModel):
    """Response of `POST /api/games/{game_id}/moves`.

    Attributes:
        user_move (UserMoveOut): The user's move.
        deviation (DeviationOut | None): Its deviation, if it was one.
        bot_move (BotMoveOut | None): The bot's reply, unless the game ended.
        state (GameStateOut): The game after both.
    """

    user_move: UserMoveOut
    deviation: DeviationOut | None
    bot_move: BotMoveOut | None
    state: GameStateOut


class MoveSummary(BaseModel):
    """One move of a finished game.

    Attributes:
        ply (int): Its ply.
        san (str): The move in SAN.
        by (Literal["user", "bot"]): Who played it.
        source (Literal["book", "engine"] | None): Where a bot move came from.
        in_theory (bool): Whether the game was in theory after it.
    """

    ply: int
    san: str
    by: Literal["user", "bot"]
    source: Literal["book", "engine"] | None
    in_theory: bool


class GameSummary(BaseModel):
    """A game with its end-of-game report.

    Attributes:
        state (GameStateOut): The final state.
        result (Literal["win", "draw", "loss"] | None): The result for the user.
        termination (str | None): Why it ended.
        variant_id (str): The line the bot followed last.
        variant_names (dict[str, str]): That line's name by locale.
        eco (str | None): That line's ECO code.
        opening (str | None): That line's catalog name.
        total_plies (int): The plies played.
        deviations (list[DeviationOut]): The user's deviations.
        moves (list[MoveSummary]): The moves.
        pgn (str): The game's PGN.
    """

    state: GameStateOut
    result: Literal["win", "draw", "loss"] | None
    termination: str | None
    variant_id: str
    variant_names: dict[str, str]
    eco: str | None
    opening: str | None
    total_plies: int
    deviations: list[DeviationOut]
    moves: list[MoveSummary]
    pgn: str


class ResumeMove(BaseModel):
    """One move of an unfinished game, to redraw it in the browser.

    Attributes:
        ply (int): Its ply.
        san (str): The move in SAN.
        uci (str): The move in UCI.
        by (Literal["user", "bot"]): Who played it.
        in_theory (bool): Whether the game was in theory after it.
        deviation (bool): Whether it was a deviation.
    """

    ply: int
    san: str
    uci: str
    by: Literal["user", "bot"]
    in_theory: bool
    deviation: bool


class ResumeSetup(BaseModel):
    """The setup of an unfinished game.

    Attributes:
        color (Literal["white", "black"]): The user's color.
        level (str): The bot's level key.
        pace (str): `instant` or `human`.
        time_control (str): The time control's key.
        variant_ids (list[str]): The selected lines.
        chess960 (Chess960Start | None): The Chess960 start, if it is one.
        ui (dict[str, bool]): The UI flags saved with the game.
    """

    color: Literal["white", "black"]
    level: str
    pace: str
    time_control: str
    variant_ids: list[str]
    chess960: Chess960Start | None
    ui: dict[str, bool]


class ResumeClocks(BaseModel):
    """The clocks of an unfinished game, as last saved.

    Attributes:
        user_ms (int | None): The user's clock.
        bot_ms (int | None): The bot's clock.
    """

    user_ms: int | None
    bot_ms: int | None


class ActiveGame(BaseModel):
    """An unfinished game, everything the browser needs to continue it.

    Attributes:
        state (GameStateOut): Its state.
        setup (ResumeSetup): Its setup.
        moves (list[ResumeMove]): Its moves.
        clocks (ResumeClocks): Its clocks.
    """

    state: GameStateOut
    setup: ResumeSetup
    moves: list[ResumeMove]
    clocks: ResumeClocks


class ActiveGameResponse(BaseModel):
    """Response of `GET /api/games/active`.

    Attributes:
        game (ActiveGame | None): The unfinished game, or None.
    """

    game: ActiveGame | None


def _chess960_start(session: GameSession) -> Chess960Start | None:
    """The Chess960 start of a game.

    Args:
        session (GameSession): The game.

    Returns:
        Chess960Start | None: Its starting position, or None for standard chess.
    """
    position = session.chess960_position
    if position is None:
        return None
    return Chess960Start(position=position, fen=chess.Board.from_chess960_pos(position).fen())


def active_game(session: GameSession) -> ActiveGame:
    """An unfinished game for the browser to continue.

    Args:
        session (GameSession): The game.

    Returns:
        ActiveGame: The game.
    """
    deviation_plies = {deviation.ply for deviation in session.deviations}
    return ActiveGame(
        state=state_out(session),
        setup=ResumeSetup(
            color="white" if session.user_color else "black",
            level=session.level,
            pace=session.pace,
            time_control=session.time_control_key,
            variant_ids=[variant.variant_id for variant in session.selection.variants],
            chess960=_chess960_start(session),
            ui=session.ui,
        ),
        moves=[
            ResumeMove(
                ply=record.ply,
                san=record.san,
                uci=record.uci,
                by=record.by,
                in_theory=record.in_theory,
                deviation=record.ply in deviation_plies,
            )
            for record in session.moves
        ],
        clocks=ResumeClocks(user_ms=session.user_clock_ms, bot_ms=session.bot_clock_ms),
    )


def opening_out(opening: tuple[str, str] | None) -> OpeningOut | None:
    """A named position for a response.

    Args:
        opening (tuple[str, str] | None): (ECO, name), or None.

    Returns:
        OpeningOut | None: The position, or None.
    """
    return OpeningOut(eco=opening[0], name=opening[1]) if opening else None


def state_out(session: GameSession) -> GameStateOut:
    """A game's state for a response.

    Args:
        session (GameSession): The game.

    Returns:
        GameStateOut: The state.
    """
    return GameStateOut(
        opening=opening_out(session.opening),
        game_id=session.game_id,
        fen=session.board.fen(),
        ply=session.ply,
        in_theory=session.in_theory,
        theory_until_ply=session.theory_until_ply,
        left_theory_at_move=session.left_theory_at_move,
        game_over=session.is_over,
        bot_deviation=deviation_out(session.bot_deviation) if session.bot_deviation else None,
    )


def bot_move_out(reply: BotReply | None) -> BotMoveOut | None:
    """The bot's move for a response.

    Args:
        reply (BotReply | None): The bot's move, or None.

    Returns:
        BotMoveOut | None: The move, or None.
    """
    if reply is None:
        return None
    record = reply.record
    return BotMoveOut(
        opening=opening_out(record.opening),
        uci=record.uci,
        san=record.san,
        ply=record.ply,
        source=record.source,
        delay_ms=reply.delay_ms,
        in_theory=record.in_theory,
    )


def deviation_out(deviation: Deviation) -> DeviationOut:
    """A deviation for a response.

    Args:
        deviation (Deviation): The deviation.

    Returns:
        DeviationOut: The deviation, with its full-move number.
    """
    return DeviationOut(
        ply=deviation.ply,
        move_number=(deviation.ply + 1) // 2,
        played_san=deviation.played_san,
        expected_san=list(deviation.expected_san),
    )


def game_summary(session: GameSession) -> GameSummary:
    """A game with its end-of-game report.

    Args:
        session (GameSession): The game.

    Returns:
        GameSummary: The summary.
    """
    return GameSummary(
        state=state_out(session),
        result=session.outcome.result if session.outcome else None,
        termination=session.outcome.termination if session.outcome else None,
        variant_id=session.variant.variant_id,
        variant_names=session.variant.names,
        eco=session.variant.eco,
        opening=session.variant.opening,
        total_plies=session.ply,
        deviations=[deviation_out(deviation) for deviation in session.deviations],
        moves=[
            MoveSummary(
                ply=record.ply,
                san=record.san,
                by=record.by,
                source=record.source,
                in_theory=record.in_theory,
            )
            for record in session.moves
        ],
        pgn=session.pgn(),
    )
