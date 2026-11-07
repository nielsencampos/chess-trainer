"""The book as the game layer sees it."""

from dataclasses import dataclass


class BookError(ValueError):
    """The book is invalid and the app must not start with it."""


@dataclass(frozen=True, slots=True)
class BookMove:
    uci: str
    san: str


@dataclass(frozen=True, slots=True)
class BookMoveRow:
    epd_before: str
    ply: int
    uci: str
    san: str


@dataclass(frozen=True)
class Variant:
    variant_id: str
    repertoire_id: str
    names: dict[str, str]
    eco: str | None
    opening: str | None
    source: str
    pgn: str
    moves: dict[str, tuple[BookMove, ...]]
    positions: frozenset[str]
    final_epd: str


@dataclass(frozen=True)
class Repertoire:
    repertoire_id: str
    names: dict[str, str]
    variant_ids: tuple[str, ...]


@dataclass(frozen=True)
class Book:
    repertoires: dict[str, Repertoire]
    variants: dict[str, Variant]


def index_moves(
    rows: list[BookMoveRow], final_epd: str
) -> tuple[dict[str, tuple[BookMove, ...]], frozenset[str]]:
    """Position -> moves, and every position on the line, including the final one."""
    by_position: dict[str, dict[str, str]] = {}
    for row in rows:
        by_position.setdefault(row.epd_before, {})[row.uci] = row.san
    moves = {
        epd: tuple(BookMove(uci, san) for uci, san in by_uci.items())
        for epd, by_uci in by_position.items()
    }
    return moves, frozenset(moves) | {final_epd}
