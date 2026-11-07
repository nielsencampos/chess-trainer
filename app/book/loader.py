"""Load repertoire PGN files. Any problem fails loudly: a bad book must never reach the bot."""

from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn

COLORS = ("white", "black")
REQUIRED_HEADERS = ("RepertoireId", "RepertoireName_en", "VariantId", "Color", "Name_en", "Source")
VARIANT_NAME_PREFIX = "Name_"
REPERTOIRE_NAME_PREFIX = "RepertoireName_"


class BookError(ValueError):
    """The repertoire is invalid and the app must not start with it."""


@dataclass(frozen=True, slots=True)
class BookMove:
    uci: str
    san: str


@dataclass(frozen=True)
class Variant:
    variant_id: str
    repertoire_id: str
    color: str
    names: dict[str, str]
    eco: str | None
    opening: str | None
    source: str
    moves_san: tuple[str, ...]
    moves: dict[str, tuple[BookMove, ...]]
    positions: frozenset[str]
    final_epd: str


@dataclass(frozen=True)
class Repertoire:
    repertoire_id: str
    color: str
    names: dict[str, str]
    variant_ids: tuple[str, ...]


@dataclass(frozen=True)
class Book:
    repertoires: dict[str, Repertoire]
    variants: dict[str, Variant]


def _localized(headers: chess.pgn.Headers, prefix: str) -> dict[str, str]:
    return {
        key.removeprefix(prefix): value
        for key, value in headers.items()
        if key.startswith(prefix) and value
    }


def _walk(game: chess.pgn.Game) -> tuple[dict[str, tuple[BookMove, ...]], frozenset[str]]:
    """Flatten the main line and all RAVs into position -> moves."""
    moves: dict[str, dict[str, str]] = {}
    positions: set[str] = set()

    def visit(node: chess.pgn.GameNode, board: chess.Board) -> None:
        epd = board.epd()
        positions.add(epd)
        for child in node.variations:
            moves.setdefault(epd, {})[child.move.uci()] = board.san(child.move)
            next_board = board.copy(stack=False)
            next_board.push(child.move)
            visit(child, next_board)

    visit(game, game.board())
    frozen = {
        epd: tuple(BookMove(uci, san) for uci, san in by_uci.items())
        for epd, by_uci in moves.items()
    }
    return frozen, frozenset(positions)


def _parse_variant(game: chess.pgn.Game, where: str) -> Variant:
    if game.errors:
        raise BookError(f"{where}: invalid PGN: {game.errors[0]}")
    headers = game.headers
    for header in REQUIRED_HEADERS:
        if not headers.get(header):
            raise BookError(f"{where}: missing header [{header}]")
    variant_id = headers["VariantId"]
    color = headers["Color"]
    if color not in COLORS:
        raise BookError(f"{variant_id}: [Color] must be one of {COLORS}, got {color!r}")
    if game.next() is None:
        raise BookError(f"{variant_id}: has no moves")

    moves, positions = _walk(game)
    return Variant(
        variant_id=variant_id,
        repertoire_id=headers["RepertoireId"],
        color=color,
        names=_localized(headers, VARIANT_NAME_PREFIX),
        eco=headers.get("ECO"),
        opening=headers.get("Opening"),
        source=headers["Source"],
        moves_san=tuple(_mainline_san(game)),
        moves=moves,
        positions=positions,
        final_epd=game.end().board().epd(),
    )


def _mainline_san(game: chess.pgn.Game) -> list[str]:
    board = game.board()
    sans = []
    for move in game.mainline_moves():
        sans.append(board.san(move))
        board.push(move)
    return sans


def load_book(directory: Path) -> Book:
    paths = sorted(directory.glob("*.pgn"))
    if not paths:
        raise BookError(f"no .pgn files in {directory}")

    variants: dict[str, Variant] = {}
    repertoires: dict[str, Repertoire] = {}
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            index = 0
            while (game := chess.pgn.read_game(handle)) is not None:
                index += 1
                variant = _parse_variant(game, f"{path.name} game {index}")
                if variant.variant_id in variants:
                    raise BookError(f"duplicate VariantId {variant.variant_id!r} in {path.name}")
                variants[variant.variant_id] = variant

                known = repertoires.get(variant.repertoire_id)
                if known is not None and known.color != variant.color:
                    raise BookError(
                        f"{variant.variant_id}: repertoire {variant.repertoire_id!r} "
                        f"mixes colors {known.color} and {variant.color}"
                    )
                repertoires[variant.repertoire_id] = Repertoire(
                    repertoire_id=variant.repertoire_id,
                    color=variant.color,
                    names=known.names
                    if known
                    else _localized(game.headers, REPERTOIRE_NAME_PREFIX),
                    variant_ids=(*(known.variant_ids if known else ()), variant.variant_id),
                )
        if index == 0:
            raise BookError(f"{path.name}: contains no games")
    return Book(repertoires=repertoires, variants=variants)
