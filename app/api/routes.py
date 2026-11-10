"""HTTP routes. Business rules stay in app.game; errors map to status codes here."""

import asyncio
import json

import chess
from fastapi import APIRouter, HTTPException, Request, Response

from app import __version__
from app.api.schemas import (
    ActiveGameResponse,
    Chess960Request,
    Chess960Start,
    DeleteRequest,
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
    RemoteImportRequest,
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
    TIME_CONTROL_GROUPS,
)
from app.game.remote import RemoteError, fetch_games
from app.game.review import pgn_of_line, review_of_pgn
from app.game.service import FromGame, GameService, InvalidSetupError, UnknownGameError
from app.game.session import (
    BotDeviationSetup,
    GameFinishedError,
    IllegalMoveError,
    NothingToTakeBackError,
    NotYourTurnError,
)

router = APIRouter(prefix="/api")

DEFAULT_LOCALE = "en"


def _service(request: Request) -> GameService:
    """The game service of the app.

    Args:
        request (Request): The HTTP request, for the app's state.

    Returns:
        GameService: The service.
    """
    return request.app.state.games


def _http_error(error: Exception) -> HTTPException:
    """Maps a game error to its HTTP status.

    Args:
        error (Exception): The error raised by the game layer.

    Returns:
        HTTPException: The response error.

    Raises:
        Exception: The same error, if it is not a game error.
    """
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
    """`GET /api/health`: app version and the engine's name and build.

    Args:
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: `status`, `app_version` and `engine`.
    """
    engine = _service(request).engine
    return {
        "status": "ok",
        "app_version": __version__,
        "engine": {"name": engine.name, "build_tag": engine.build_tag},
    }


@router.get("/repertoires")
async def repertoires(request: Request) -> dict:
    """`GET /api/repertoires`: the book, by group and order, with each family's active lines.

    Args:
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: `repertoires`, each with its `variants`.
    """
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


@router.get("/locales")
async def locales(request: Request) -> dict:
    """`GET /api/locales`: the languages with a UI file in web/i18n, English first.

    Each is named in its own language.

    Args:
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: `locales` (code and name) and the `default` code.
    """
    found = []
    for path in sorted(request.app.state.i18n_dir.glob("*.json")):
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("locale.name", path.stem)
        except (OSError, ValueError):
            continue  # A broken file is left out; the frontend falls back to English.
        found.append({"code": path.stem, "name": name})
    found.sort(key=lambda item: (item["code"] != DEFAULT_LOCALE, item["code"]))
    return {"locales": found, "default": DEFAULT_LOCALE}


@router.get("/engine/levels")
async def levels(request: Request) -> dict:
    """`GET /api/engine/levels`: the bot's levels, weakest first, with their nominal ratings.

    Args:
        request (Request): The request, for the levels loaded at start.

    Returns:
        dict: `levels`, the `elo` shown beside each level's name, and the `default` level.
    """
    loaded = request.app.state.levels
    return {
        "levels": list(LEVEL_ORDER),
        "elo": {key: loaded[key].elo for key in LEVEL_ORDER},
        "default": "club",
    }


@router.get("/time-controls")
async def time_controls() -> dict:
    """`GET /api/time-controls`: the clock presets by category.

    Returns:
        dict: `groups` of presets, the `no_clock` key and the `default` key.
    """
    return {
        "groups": [
            {
                "key": group,
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
    """`POST /api/games`: starts a new game, abandoning an active one.

    Args:
        body (NewGameRequest): The setup.
        request (Request): The HTTP request, for the app's state.

    Returns:
        NewGameResponse: The game and the bot's first move, if it starts.

    Raises:
        HTTPException: 404 for an unknown game, 409 or 422 for a refused action, 503 without engine.
    """
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
            BotDeviationSetup(body.bot_deviation.from_move, body.bot_deviation.chance)
            if body.bot_deviation
            else None,
        )
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return NewGameResponse(state=state_out(session), bot_move=bot_move_out(reply))


@router.post("/chess960")
async def chess960_start(body: Chess960Request, request: Request) -> Chess960Start:
    """`POST /api/chess960`: a Chess960 starting position, rolled or from a typed FEN.

    Args:
        body (Chess960Request): The FEN, or none to roll.
        request (Request): The HTTP request, for the app's state.

    Returns:
        Chess960Start: The position.

    Raises:
        HTTPException: 422 if the FEN is not a Chess960 starting position.
    """
    try:
        position, fen = _service(request).chess960_start(body.fen)
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return Chess960Start(position=position, fen=fen)


@router.post("/evaluate")
async def evaluate(body: EvaluateRequest, request: Request) -> EvaluationOut:
    """`POST /api/evaluate`: Stockfish's evaluation of the position on screen.

    Args:
        body (EvaluateRequest): The position.
        request (Request): The HTTP request, for the app's state.

    Returns:
        EvaluationOut: The evaluation from White's side.

    Raises:
        HTTPException: 422 for an invalid position, 503 if the engine is unavailable.
    """
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
    """`GET /api/games`: the finished games, newest first.

    Args:
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: `games`.
    """
    return {"games": _service(request).store.finished_games()}


@router.post("/games/import")
async def import_games(body: ImportRequest, request: Request) -> dict:
    """`POST /api/games/import`: imports pasted or uploaded PGN.

    Args:
        body (ImportRequest): The PGN text.
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: The import report: counts and refused games.
    """
    return _service(request).import_pgn(body.pgn)


@router.post("/games/import/remote")
async def import_remote_games(body: RemoteImportRequest, request: Request) -> dict:
    """`POST /api/games/import/remote`: a player's public games from Chess.com or Lichess.

    They go through the same import as a paste.

    Args:
        body (RemoteImportRequest): The site, username and period.
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: The import report, plus `fetched` and `truncated`.

    Raises:
        HTTPException: 422 bad username, 404 unknown user, 429 rate limited, 502 otherwise.
    """
    try:
        fetched = await asyncio.to_thread(
            fetch_games, body.site, body.username, body.months, request.app.state.fetch_url
        )
    except RemoteError as error:
        status = {"bad_username": 422, "user_not_found": 404, "rate_limited": 429}
        raise HTTPException(status.get(error.code, 502), error.code) from error
    report = _service(request).import_pgn(fetched.pgn) if fetched.games else _EMPTY_REPORT
    return {**report, "fetched": fetched.games, "truncated": fetched.truncated}


_EMPTY_REPORT = {"imported": 0, "duplicates": 0, "updated": 0, "errors": []}


@router.post("/games/delete")
async def delete_games(body: DeleteRequest, request: Request) -> dict:
    """`POST /api/games/delete`: deletes saved games for good.

    Nothing is deleted if any of them is unknown or still being played.

    Args:
        body (DeleteRequest): The games.
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: `deleted`, the number of games deleted.

    Raises:
        HTTPException: 422 if a game is not a finished one.
    """
    store = _service(request).store
    missing = sorted(set(body.game_ids) - set(store.finished_pgns(body.game_ids)))
    if missing:
        raise HTTPException(422, f"not a finished game: {missing[0]}")
    return {"deleted": store.delete_finished(body.game_ids)}


@router.post("/games/export")
async def export_games(body: ExportRequest, request: Request) -> Response:
    """`POST /api/games/export`: the selected games as one PGN file, oldest first.

    Args:
        body (ExportRequest): The games.
        request (Request): The HTTP request, for the app's state.

    Returns:
        Response: The PGN file as an attachment.

    Raises:
        HTTPException: 422 if a game is not a finished one.
    """
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
    """`GET /api/games/{game_id}/review`: a saved game for the read-only board.

    Args:
        game_id (str): The game's id.
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: The review's moves and the game's players, result and opening.

    Raises:
        HTTPException: 404 if the game is unknown or unfinished.
    """
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
        "chess960": game["chess960"],
        "source": game["source"],
        "user_color": game["user_color"],
        "level": game["level"],
    }


@router.post("/lines/export")
async def export_lines(body: ExportLinesRequest, request: Request) -> Response:
    """`POST /api/lines/export`: the ticked book lines as one PGN file.

    Args:
        body (ExportLinesRequest): The lines.
        request (Request): The HTTP request, for the app's state.

    Returns:
        Response: The PGN file as an attachment.

    Raises:
        HTTPException: 422 for an unknown line.
    """
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
    """Marks a game's review moves as book or deviation; only a game played here knows them.

    Args:
        moves (list[dict]): The review's main-line moves.
        game (dict): The saved game, with its moves and both sides' deviations.

    Returns:
        list[dict]: The moves, with `book`, `deviation` and `bot_deviation` for a game played
            here.
    """
    records = json.loads(game["moves_json"]) if game.get("moves_json") else []
    deviations = {item["ply"] for item in json.loads(game.get("deviations_json") or "[]")}
    bot = (json.loads(game.get("bot_deviation_json") or "{}") or {}).get("deviation")
    bot_ply = bot["ply"] if bot else None
    if game.get("source") != "app" or len(records) != len(moves):
        return moves
    return [
        {
            **move,
            "book": bool(record["in_theory"]),
            "deviation": move["ply"] in deviations,
            "bot_deviation": move["ply"] == bot_ply,
        }
        for move, record in zip(moves, records, strict=True)
    ]


@router.get("/lines/{variant_id}/review")
async def review_line(variant_id: str, request: Request) -> dict:
    """`GET /api/lines/{variant_id}/review`: a book line for the read-only board.

    Args:
        variant_id (str): The line id.
        request (Request): The HTTP request, for the app's state.

    Returns:
        dict: The review's moves, all of them book moves, and the line's opening.

    Raises:
        HTTPException: 404 for an unknown line.
    """
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
    """`GET /api/games/active`: the unfinished game, after the bot's pending reply.

    Args:
        request (Request): The HTTP request, for the app's state.

    Returns:
        ActiveGameResponse: The game, or none.

    Raises:
        HTTPException: 404 for an unknown game, 409 or 422 for a refused action, 503 without engine.
    """
    try:
        session = await _service(request).resume_active()
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return ActiveGameResponse(game=active_game(session) if session else None)


@router.post("/games/{game_id}/moves")
async def post_move(game_id: str, body: MoveRequest, request: Request) -> MoveResponse:
    """`POST /api/games/{game_id}/moves`: plays the user's move and the bot's reply.

    Args:
        game_id (str): The game's id.
        body (MoveRequest): The move and the clocks.
        request (Request): The HTTP request, for the app's state.

    Returns:
        MoveResponse: Both moves, the deviation if any, and the state.

    Raises:
        HTTPException: 404 for an unknown game, 409 or 422 for a refused action, 503 without engine.
    """
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
    """`POST /api/games/{game_id}/resign`: resigns the game.

    Args:
        game_id (str): The game's id.
        request (Request): The HTTP request, for the app's state.

    Returns:
        GameSummary: The finished game.

    Raises:
        HTTPException: 404 for an unknown game, 409 or 422 for a refused action, 503 without engine.
    """
    try:
        return game_summary(_service(request).resign(game_id))
    except GAME_ERRORS as error:
        raise _http_error(error) from error


@router.post("/games/{game_id}/takeback")
async def take_back(game_id: str, body: TakeBackRequest, request: Request) -> GameStateOut:
    """`POST /api/games/{game_id}/takeback`: takes back the user's last move.

    Args:
        game_id (str): The game's id.
        body (TakeBackRequest): The shown plies and the clocks before the move.
        request (Request): The HTTP request, for the app's state.

    Returns:
        GameStateOut: The state after the take-back.

    Raises:
        HTTPException: 404 for an unknown game, 409 or 422 for a refused action, 503 without engine.
    """
    try:
        session = _service(request).take_back(
            game_id, body.shown_plies, body.user_clock_ms, body.bot_clock_ms
        )
    except GAME_ERRORS as error:
        raise _http_error(error) from error
    return state_out(session)


@router.post("/games/{game_id}/timeout")
async def timeout(game_id: str, body: FlagRequest, request: Request) -> GameSummary:
    """`POST /api/games/{game_id}/timeout`: ends the game when a clock in the browser runs out.

    Args:
        game_id (str): The game's id.
        body (FlagRequest): Whose clock ran out and the shown plies.
        request (Request): The HTTP request, for the app's state.

    Returns:
        GameSummary: The finished game.

    Raises:
        HTTPException: 404 for an unknown game, 409 or 422 for a refused action, 503 without engine.
    """
    try:
        return game_summary(_service(request).flag(game_id, body.side, body.shown_plies))
    except GAME_ERRORS as error:
        raise _http_error(error) from error


@router.get("/games/{game_id}")
async def get_game(game_id: str, request: Request) -> GameSummary:
    """`GET /api/games/{game_id}`: a game in memory with its report.

    Args:
        game_id (str): The game's id.
        request (Request): The HTTP request, for the app's state.

    Returns:
        GameSummary: The game.

    Raises:
        HTTPException: 404 for an unknown game, 409 or 422 for a refused action, 503 without engine.
    """
    try:
        return game_summary(_service(request).get(game_id))
    except GAME_ERRORS as error:
        raise _http_error(error) from error
