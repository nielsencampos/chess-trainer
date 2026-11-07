"""HTTP routes. Business rules stay in app.game; errors map to status codes here."""

from fastapi import APIRouter, HTTPException, Request

from app import __version__
from app.api.schemas import (
    FlagRequest,
    GameSummary,
    MoveRequest,
    MoveResponse,
    NewGameRequest,
    NewGameResponse,
    UserMoveOut,
    bot_move_out,
    deviation_out,
    game_summary,
    state_out,
)
from app.engine.levels import LEVEL_ORDER
from app.engine.process import EngineUnavailableError
from app.game.pace import (
    DEFAULT_TIME_CONTROL,
    NO_CLOCK,
    SCORESHEET_GROUPS,
    TIME_CONTROL_GROUPS,
)
from app.game.service import GameService, InvalidSetupError, UnknownGameError
from app.game.session import GameFinishedError, IllegalMoveError, NotYourTurnError

router = APIRouter(prefix="/api")


def _service(request: Request) -> GameService:
    return request.app.state.games


def _http_error(error: Exception) -> HTTPException:
    match error:
        case UnknownGameError():
            return HTTPException(404, "game not found")
        case IllegalMoveError():
            return HTTPException(422, f"illegal move: {error}")
        case GameFinishedError():
            return HTTPException(409, "game is already over")
        case NotYourTurnError():
            return HTTPException(409, "not your turn")
        case InvalidSetupError():
            return HTTPException(422, str(error))
        case EngineUnavailableError():
            return HTTPException(503, "engine unavailable")
    raise error


GAME_ERRORS = (
    UnknownGameError,
    IllegalMoveError,
    GameFinishedError,
    NotYourTurnError,
    InvalidSetupError,
    EngineUnavailableError,
)


@router.get("/health")
async def health(request: Request) -> dict:
    engine = _service(request).engine
    return {
        "status": "ok",
        "app_version": __version__,
        "engine": {"name": engine.name, "build_tag": engine.build_tag},
    }


@router.get("/repertoires")
async def repertoires(request: Request) -> dict:
    book = _service(request).book
    return {
        "repertoires": [
            {
                "repertoire_id": repertoire.repertoire_id,
                "names": repertoire.names,
                "variants": [
                    {
                        "variant_id": variant.variant_id,
                        "names": variant.names,
                        "eco": variant.eco,
                        "opening": variant.opening,
                        "pgn": variant.pgn,
                    }
                    for variant in (book.variants[key] for key in repertoire.variant_ids)
                ],
            }
            for repertoire in book.repertoires.values()
        ]
    }


@router.get("/engine/levels")
async def levels() -> dict:
    return {"levels": list(LEVEL_ORDER), "default": "club"}


@router.get("/time-controls")
async def time_controls() -> dict:
    return {
        "groups": [
            {
                "key": group,
                "scoresheet": group in SCORESHEET_GROUPS,
                "items": [
                    {
                        "key": key,
                        "base_ms": control.base_ms,
                        "increment_ms": control.increment_ms,
                        "moves_to_bonus": control.moves_to_bonus,
                        "bonus_ms": control.bonus_ms,
                    }
                    for key, control in controls.items()
                ],
            }
            for group, controls in TIME_CONTROL_GROUPS.items()
        ],
        "no_clock": NO_CLOCK,
        "default": DEFAULT_TIME_CONTROL,
    }


@router.post("/games", status_code=201)
async def create_game(body: NewGameRequest, request: Request) -> NewGameResponse:
    try:
        session, reply = await _service(request).create_game(
            body.color, body.variant_ids, body.level, body.pace, body.time_control
        )
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return NewGameResponse(state=state_out(session), bot_move=bot_move_out(reply))


@router.post("/games/{game_id}/moves")
async def post_move(game_id: str, body: MoveRequest, request: Request) -> MoveResponse:
    try:
        session, record, deviation, reply = await _service(request).user_move(
            game_id, body.uci, body.user_clock_ms, body.bot_clock_ms, body.think_ms
        )
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return MoveResponse(
        user_move=UserMoveOut(
            uci=record.uci, san=record.san, ply=record.ply, in_theory=record.in_theory
        ),
        deviation=deviation_out(deviation) if deviation else None,
        bot_move=bot_move_out(reply),
        state=state_out(session),
    )


@router.post("/games/{game_id}/resign")
async def resign(game_id: str, request: Request) -> GameSummary:
    try:
        return game_summary(_service(request).resign(game_id))
    except GAME_ERRORS as error:
        raise _http_error(error) from error


@router.post("/games/{game_id}/timeout")
async def timeout(game_id: str, body: FlagRequest, request: Request) -> GameSummary:
    try:
        return game_summary(_service(request).flag(game_id, body.side, body.shown_plies))
    except GAME_ERRORS as error:
        raise _http_error(error) from error


@router.get("/games/{game_id}")
async def get_game(game_id: str, request: Request) -> GameSummary:
    try:
        return game_summary(_service(request).get(game_id))
    except GAME_ERRORS as error:
        raise _http_error(error) from error
