"""HTTP routes. Business rules stay in app.game; errors map to status codes here."""

import json

import chess
from fastapi import APIRouter, HTTPException, Request, Response

from app import __version__
from app.api.schemas import (
    ActiveGameResponse,
    Chess960Request,
    Chess960Start,
    EvaluateRequest,
    EvaluationOut,
    ExportLinesRequest,
    ExportRequest,
    FlagRequest,
    GameStateOut,
    GameSummary,
    ImportRequest,
    MoveRequest,
    MoveResponse,
    NewGameRequest,
    NewGameResponse,
    TakeBackRequest,
    UserMoveOut,
    active_game,
    bot_move_out,
    deviation_out,
    game_summary,
    opening_out,
    state_out,
)
from app.book.source import GROUPS
from app.engine.levels import LEVEL_ORDER
from app.engine.process import EngineUnavailableError
from app.game.pace import (
    DEFAULT_TIME_CONTROL,
    NO_CLOCK,
    SCORESHEET_GROUPS,
    TIME_CONTROL_GROUPS,
)
from app.game.review import pgn_of_line, review_of_pgn
from app.game.service import FromGame, GameService, InvalidSetupError, UnknownGameError
from app.game.session import (
    GameFinishedError,
    IllegalMoveError,
    NothingToTakeBackError,
    NotYourTurnError,
)

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
        case NothingToTakeBackError():
            return HTTPException(409, "nothing to take back")
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
    NothingToTakeBackError,
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
                "group": repertoire.group,
                "order": repertoire.order,
                "variants": [
                    {
                        "variant_id": variant.variant_id,
                        "names": variant.names,
                        "eco": variant.eco,
                        "opening": variant.opening,
                        "pgn": variant.pgn,
                        "subgroup": variant.subgroup,
                    }
                    for variant in (book.variants[key] for key in repertoire.variant_ids)
                ],
            }
            for repertoire in sorted(
                book.repertoires.values(),
                key=lambda item: (
                    GROUPS.index(item.group),
                    item.order is None,
                    item.order or 0,
                    item.names.get("en", ""),
                ),
            )
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
                        "periods": [
                            {"after_moves": period.after_moves, "add_ms": period.add_ms}
                            for period in control.periods
                        ],
                        "delay_ms": control.delay_ms,
                        "delay_kind": control.delay_kind,
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
            body.color,
            body.variant_ids,
            body.level,
            body.pace,
            body.time_control,
            body.ui,
            FromGame(
                body.from_game.game_id,
                body.from_game.upto_ply,
                body.from_game.mode == "position",
            )
            if body.from_game
            else None,
            body.chess960_position,
        )
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return NewGameResponse(state=state_out(session), bot_move=bot_move_out(reply))


@router.post("/chess960")
async def chess960_start(body: Chess960Request, request: Request) -> Chess960Start:
    try:
        position, fen = _service(request).chess960_start(body.fen)
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return Chess960Start(position=position, fen=fen)


@router.post("/evaluate")
async def evaluate(body: EvaluateRequest, request: Request) -> EvaluationOut:
    try:
        board = chess.Board(body.fen, chess960=body.chess960)
    except ValueError as error:
        raise HTTPException(422, "invalid position") from error
    if not board.is_valid():
        raise HTTPException(422, "invalid position")
    try:
        result = await request.app.state.evaluator.evaluate(board)
    except EngineUnavailableError as error:
        raise HTTPException(503, "engine unavailable") from error
    return EvaluationOut(cp=result.cp, mate=result.mate, best=result.best)


@router.get("/games")
async def saved_games(request: Request) -> dict:
    return {"games": _service(request).store.finished_games()}


@router.post("/games/import")
async def import_games(body: ImportRequest, request: Request) -> dict:
    return _service(request).import_pgn(body.pgn)


@router.post("/games/export")
async def export_games(body: ExportRequest, request: Request) -> Response:
    pgns = _service(request).store.finished_pgns(body.game_ids)
    missing = sorted(set(body.game_ids) - set(pgns))
    if missing:
        raise HTTPException(422, f"not a finished game: {missing[0]}")
    return Response(
        content="\n\n".join(pgns.values()) + "\n",
        media_type="application/x-chess-pgn",
        headers={"Content-Disposition": 'attachment; filename="chess-trainer.pgn"'},
    )


@router.get("/games/{game_id}/review")
async def review_game(game_id: str, request: Request) -> dict:
    game = _service(request).store.finished_game(game_id)
    review = review_of_pgn(game["pgn"]) if game else None
    if review is None:
        raise HTTPException(404, "game not found")
    return {
        **review,
        "moves": _with_theory(review["moves"], game),
        "white": game["white"],
        "black": game["black"],
        "result": game["result"],
        "eco": game["eco"],
        "opening": game["opening"],
        "chess960": "chess960" in game["pgn"].lower(),
    }


@router.post("/lines/export")
async def export_lines(body: ExportLinesRequest, request: Request) -> Response:
    variants = _service(request).book.variants
    missing = sorted(set(body.variant_ids) - set(variants))
    if missing:
        raise HTTPException(422, f"unknown line: {missing[0]}")
    wanted = set(body.variant_ids)
    pgns = [pgn_of_line(variant) for key, variant in variants.items() if key in wanted]
    return Response(
        content="\n\n".join(pgns) + "\n",
        media_type="application/x-chess-pgn",
        headers={"Content-Disposition": 'attachment; filename="chess-trainer-lines.pgn"'},
    )


def _with_theory(moves: list[dict], game: dict) -> list[dict]:
    """A game played here knows which moves were book and which one left it."""
    records = json.loads(game["moves_json"]) if game.get("moves_json") else []
    deviations = {item["ply"] for item in json.loads(game.get("deviations_json") or "[]")}
    if game.get("source") != "app" or len(records) != len(moves):
        return moves
    return [
        {**move, "book": bool(record["in_theory"]), "deviation": move["ply"] in deviations}
        for move, record in zip(moves, records, strict=True)
    ]


@router.get("/lines/{variant_id}/review")
async def review_line(variant_id: str, request: Request) -> dict:
    variant = _service(request).book.variants.get(variant_id)
    review = review_of_pgn(f"{variant.pgn} *") if variant else None
    if review is None:
        raise HTTPException(404, "line not found")
    return {
        **review,
        "moves": [{**move, "book": True, "deviation": False} for move in review["moves"]],
        "white": None,
        "black": None,
        "result": None,
        "eco": variant.eco,
        "opening": variant.opening,
        "chess960": False,
    }


@router.get("/games/active")
async def get_active_game(request: Request) -> ActiveGameResponse:
    try:
        session = await _service(request).resume_active()
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return ActiveGameResponse(game=active_game(session) if session else None)


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
            opening=opening_out(record.opening),
            uci=record.uci,
            san=record.san,
            ply=record.ply,
            in_theory=record.in_theory,
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


@router.post("/games/{game_id}/takeback")
async def take_back(game_id: str, body: TakeBackRequest, request: Request) -> GameStateOut:
    try:
        session = _service(request).take_back(
            game_id, body.shown_plies, body.user_clock_ms, body.bot_clock_ms
        )
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return state_out(session)


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
