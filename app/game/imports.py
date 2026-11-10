"""Reads games out of PGN text. One bad game never stops the others from being read."""

import hashlib
import io
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import chess
import chess.pgn

from app.game.review import COMMAND

MAX_GAMES = 5000


@dataclass(frozen=True)
class ImportError_:
    """Why one game of a PGN text was refused.

    Attributes:
        index (int): The game's place in the text, from 1.
        label (str): "White - Black", to find it.
        code (str): The reason, translated by the UI, such as `invalid_moves`.
        detail (str): Extra text for the reason, such as the illegal move.
    """

    index: int
    label: str
    code: str
    detail: str = ""


@dataclass(frozen=True)
class ImportedGame:
    """A game read from PGN, ready to be saved.

    Attributes:
        white (str): White's name.
        black (str): Black's name.
        played_at (datetime): The PGN date, or now if it has none.
        result (str): The PGN result, such as `1-0`.
        time_control (str): The PGN `TimeControl` tag, or `?`.
        eco (str | None): The ECO code, from the PGN or the catalog.
        opening (str | None): The opening name, from the PGN or the catalog.
        sans (tuple[str, ...]): The main line in SAN.
        ucis (tuple[str, ...]): The main line in UCI.
        pgn (str): The game as PGN, with comments and side variations.
        content_hash (str): Hash of players, date and moves, to find duplicates.
        notes (int): How much analysis it carries (`annotation_count`).
    """

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
    notes: int = 0


def annotation_count(game: chess.pgn.Game) -> int:
    """How much analysis a game carries: NAGs, evaluations, text comments, side variations.

    Clocks and other commands do not count, so a site's plain export scores 0 and the same game
    downloaded with its analysis scores more.

    Args:
        game (chess.pgn.Game): The game.

    Returns:
        int: The number of annotations.
    """
    count = 0
    for node in _all_nodes(game):
        if node is not game:
            count += bool(node.nags) + (node.eval() is not None)
        count += bool(COMMAND.sub(" ", node.comment).strip()) + len(node.variations[1:])
    return count


def annotation_count_of(pgn: str) -> int:
    """`annotation_count` of a game given as PGN text.

    Args:
        pgn (str): One PGN game.

    Returns:
        int: The number of annotations, 0 if the PGN has no game.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    return annotation_count(game) if game is not None else 0


def _all_nodes(node: chess.pgn.GameNode) -> Iterator[chess.pgn.GameNode]:
    """Every node of a game tree, side variations included, depth first.

    Args:
        node (chess.pgn.GameNode): The root.

    Yields:
        chess.pgn.GameNode: The root, then each node under it.
    """
    yield node
    for child in node.variations:
        yield from _all_nodes(child)


def content_hash(white: str, black: str, date: str, ucis: tuple[str, ...]) -> str:
    """Identifies a game: the same game is the same players, date and moves, wherever it came from.

    Args:
        white (str): White's name.
        black (str): Black's name.
        date (str): The PGN date.
        ucis (tuple[str, ...]): The main line in UCI.

    Returns:
        str: The SHA-256 hex digest.
    """
    text = f"{white}|{black}|{date}|{' '.join(ucis)}"
    return hashlib.sha256(text.encode()).hexdigest()


def _played_at(date: str) -> datetime:
    """Reads a PGN date.

    Args:
        date (str): The date as `YYYY.MM.DD`.

    Returns:
        datetime: Midnight UTC of that day, or now if the date is missing or partial.
    """
    try:
        return datetime.strptime(date, "%Y.%m.%d").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _read_one(
    game: chess.pgn.Game, opening_names: Mapping[str, tuple[str, str]]
) -> ImportedGame | tuple[str, str]:
    """Reads one game, or says why it is refused.

    Args:
        game (chess.pgn.Game): The game as parsed.
        opening_names (Mapping[str, tuple[str, str]]): Position (EPD) -> (ECO, catalog name).

    Returns:
        ImportedGame | tuple[str, str]: The game, or the (code, detail) of why it was refused.
    """
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
    exporter = chess.pgn.StringExporter()  # side variations are kept for the review
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
        notes=annotation_count(game),
    )


def read_pgn_text(
    text: str, opening_names: Mapping[str, tuple[str, str]]
) -> tuple[list[ImportedGame], list[ImportError_]]:
    """Reads every game of a PGN text, up to `MAX_GAMES`. A bad game never stops the others.

    Args:
        text (str): One or more PGN games.
        opening_names (Mapping[str, tuple[str, str]]): Position (EPD) -> (ECO, catalog name).

    Returns:
        tuple[list[ImportedGame], list[ImportError_]]: The games read and the ones refused.
    """
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
