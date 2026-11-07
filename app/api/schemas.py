"""Request and response bodies of the HTTP API."""

from typing import Literal

from pydantic import BaseModel, Field

from app.game.service import BotReply
from app.game.session import Deviation, GameSession


class FromGameRequest(BaseModel):
    game_id: str
    upto_ply: int | None = Field(default=None, ge=1)
    mode: Literal["line", "position"] = "line"


class NewGameRequest(BaseModel):
    color: Literal["white", "black"]
    variant_ids: list[str] = Field(default_factory=list)
    from_game: FromGameRequest | None = None
    level: str
    pace: Literal["instant", "human"]
    time_control: str
    ui: dict[str, bool] = Field(default_factory=dict)


class MoveRequest(BaseModel):
    uci: str = Field(min_length=4, max_length=5)
    user_clock_ms: int | None = Field(default=None, ge=0)
    bot_clock_ms: int | None = Field(default=None, ge=0)
    think_ms: int | None = Field(default=None, ge=0)


class ImportRequest(BaseModel):
    pgn: str = Field(max_length=50_000_000)


class ExportRequest(BaseModel):
    game_ids: list[str] = Field(min_length=1)


class FlagRequest(BaseModel):
    side: Literal["user", "bot"]
    shown_plies: int = Field(ge=0)


class OpeningOut(BaseModel):
    eco: str
    name: str


class BotMoveOut(BaseModel):
    opening: OpeningOut | None = None
    uci: str
    san: str
    ply: int
    source: Literal["book", "engine"]
    delay_ms: int
    in_theory: bool


class GameStateOut(BaseModel):
    opening: OpeningOut | None = None
    game_id: str
    fen: str
    ply: int
    in_theory: bool
    theory_until_ply: int
    left_theory_at_move: int | None
    game_over: bool


class NewGameResponse(BaseModel):
    state: GameStateOut
    bot_move: BotMoveOut | None


class UserMoveOut(BaseModel):
    opening: OpeningOut | None = None
    uci: str
    san: str
    ply: int
    in_theory: bool


class DeviationOut(BaseModel):
    ply: int
    move_number: int
    played_san: str
    expected_san: list[str]


class MoveResponse(BaseModel):
    user_move: UserMoveOut
    deviation: DeviationOut | None
    bot_move: BotMoveOut | None
    state: GameStateOut


class MoveSummary(BaseModel):
    ply: int
    san: str
    by: Literal["user", "bot"]
    source: Literal["book", "engine"] | None
    in_theory: bool


class GameSummary(BaseModel):
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
    lichess_url: str


class ResumeMove(BaseModel):
    ply: int
    san: str
    uci: str
    by: Literal["user", "bot"]
    in_theory: bool
    deviation: bool


class ResumeSetup(BaseModel):
    color: Literal["white", "black"]
    level: str
    pace: str
    time_control: str
    variant_ids: list[str]
    ui: dict[str, bool]


class ResumeClocks(BaseModel):
    user_ms: int | None
    bot_ms: int | None


class ActiveGame(BaseModel):
    state: GameStateOut
    setup: ResumeSetup
    moves: list[ResumeMove]
    clocks: ResumeClocks


class ActiveGameResponse(BaseModel):
    game: ActiveGame | None


def active_game(session: GameSession) -> ActiveGame:
    deviation_plies = {deviation.ply for deviation in session.deviations}
    return ActiveGame(
        state=state_out(session),
        setup=ResumeSetup(
            color="white" if session.user_color else "black",
            level=session.level,
            pace=session.pace,
            time_control=session.time_control_key,
            variant_ids=[variant.variant_id for variant in session.selection.variants],
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
    return OpeningOut(eco=opening[0], name=opening[1]) if opening else None


def state_out(session: GameSession) -> GameStateOut:
    return GameStateOut(
        opening=opening_out(session.opening),
        game_id=session.game_id,
        fen=session.board.fen(),
        ply=session.ply,
        in_theory=session.in_theory,
        theory_until_ply=session.theory_until_ply,
        left_theory_at_move=session.left_theory_at_move,
        game_over=session.is_over,
    )


def bot_move_out(reply: BotReply | None) -> BotMoveOut | None:
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
    return DeviationOut(
        ply=deviation.ply,
        move_number=(deviation.ply + 1) // 2,
        played_san=deviation.played_san,
        expected_san=list(deviation.expected_san),
    )


def game_summary(session: GameSession) -> GameSummary:
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
        lichess_url=session.lichess_url(),
    )
