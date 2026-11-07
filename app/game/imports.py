"""Reads games out of PGN text. One bad game never stops the others from being read."""

import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import chess
import chess.pgn

MAX_GAMES = 5000


@dataclass(frozen=True)
class ImportError_:
    index: int
    label: str
    code: str
    detail: str = ""


@dataclass(frozen=True)
class ImportedGame:
    white: str
    black: str
    played_at: datetime
    result: str
    time_control: str
    eco: str | None
    opening: str | None
    sans: tuple[str, ...]
    ucis: tuple[str, ...]
    pgn: str
    content_hash: str


def content_hash(white: str, black: str, date: str, ucis: tuple[str, ...]) -> str:
    """The same game is the same players, date and moves, wherever it came from."""
    text = f"{white}|{black}|{date}|{' '.join(ucis)}"
    return hashlib.sha256(text.encode()).hexdigest()


def _played_at(date: str) -> datetime:
    try:
        return datetime.strptime(date, "%Y.%m.%d").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _read_one(
    game: chess.pgn.Game, opening_names: Mapping[str, tuple[str, str]]
) -> ImportedGame | tuple[str, str]:
    """The game, or the (code, detail) of why it was refused."""
    if game.errors:
        return "invalid_moves", str(game.errors[0])
    headers = game.headers
    is_960 = headers.is_chess960()
    if "FEN" in headers and not is_960:
        return "custom_position", ""
    board = game.board()
    if board.uci_variant != "chess":
        return "unsupported_variant", headers.get("Variant", "")

    sans: list[str] = []
    ucis: list[str] = []
    named: tuple[str, str] | None = None
    for move in game.mainline_moves():
        sans.append(board.san(move))
        ucis.append(move.uci())
        board.push(move)
        named = opening_names.get(board.epd(), named)
    if not sans:
        return "no_moves", ""

    # A name and its ECO must come from the same place: the PGN's tags or the catalog.
    if "Opening" in headers:
        eco, opening = headers.get("ECO"), headers["Opening"]
    elif named and not is_960:  # catalog names do not apply to a shuffled start
        eco, opening = named
    else:
        eco, opening = headers.get("ECO"), None

    white, black, date = (
        headers.get("White", "?"),
        headers.get("Black", "?"),
        headers.get("Date", ""),
    )
    exporter = chess.pgn.StringExporter(variations=False)  # side variations are dropped
    return ImportedGame(
        white=white,
        black=black,
        played_at=_played_at(date),
        result=headers.get("Result", "*"),
        time_control=headers.get("TimeControl", "?"),
        eco=eco,
        opening=opening,
        sans=tuple(sans),
        ucis=tuple(ucis),
        pgn=game.accept(exporter).strip(),
        content_hash=content_hash(white, black, date, tuple(ucis)),
    )


def read_pgn_text(
    text: str, opening_names: Mapping[str, tuple[str, str]]
) -> tuple[list[ImportedGame], list[ImportError_]]:
    games: list[ImportedGame] = []
    errors: list[ImportError_] = []
    handle = io.StringIO(text)
    index = 0
    while (game := chess.pgn.read_game(handle)) is not None and index < MAX_GAMES:
        index += 1
        label = f"{game.headers.get('White', '?')} - {game.headers.get('Black', '?')}"
        outcome = _read_one(game, opening_names)
        if isinstance(outcome, ImportedGame):
            games.append(outcome)
        else:
            errors.append(ImportError_(index, label, outcome[0], outcome[1]))
    return games, errors
