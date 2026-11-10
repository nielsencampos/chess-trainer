"""The book as the game layer sees it."""

from dataclasses import dataclass


class BookError(ValueError):
    """The book is invalid and the app must not start with it."""


@dataclass(frozen=True, slots=True)
class BookMove:
    """A move of the book from a position.

    Attributes:
        uci (str): The move in UCI.
        san (str): The move in SAN.
    """

    uci: str
    san: str


@dataclass(frozen=True, slots=True)
class BookMoveRow:
    """A row of `book_moves`: one move of one line.

    Attributes:
        epd_before (str): The position before the move.
        ply (int): The move's ply on the line, from 1.
        uci (str): The move in UCI.
        san (str): The move in SAN.
    """

    epd_before: str
    ply: int
    uci: str
    san: str


@dataclass(frozen=True)
class Variant:
    """A line of the book, as loaded from the database.

    Attributes:
        variant_id (str): The line id, which never changes.
        repertoire_id (str): The family the line belongs to.
        names (dict[str, str]): The line's name by locale.
        eco (str | None): The ECO code, if known.
        opening (str | None): The catalog name of the final position, if the line has one.
        source (str): Where the line came from.
        pgn (str): The moves as PGN movetext.
        moves (dict[str, tuple[BookMove, ...]]): Position (EPD) -> the line's move from it.
        positions (frozenset[str]): Every position on the line, the final one included.
        final_epd (str): The position after the last move.
        subgroup (dict[str, str] | None): The subgroup's name by locale, or None for a loose line.
    """

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
    subgroup: dict[str, str] | None = None


@dataclass(frozen=True)
class Repertoire:
    """An opening family.

    Attributes:
        repertoire_id (str): The family id, the name of its file.
        names (dict[str, str]): The family's name by locale.
        variant_ids (tuple[str, ...]): Its active lines, in file order.
        group (str): Its group, such as `kings-pawn`.
        order (int | None): Its place in the group, or None for "Others".
    """

    repertoire_id: str
    names: dict[str, str]
    variant_ids: tuple[str, ...]
    group: str = "others"
    order: int | None = None


@dataclass(frozen=True)
class Book:
    """The whole book.

    Attributes:
        repertoires (dict[str, Repertoire]): The families by id.
        variants (dict[str, Variant]): The active lines by id.
    """

    repertoires: dict[str, Repertoire]
    variants: dict[str, Variant]


def index_moves(
    rows: list[BookMoveRow], final_epd: str
) -> tuple[dict[str, tuple[BookMove, ...]], frozenset[str]]:
    """Indexes a line's moves by position.

    Args:
        rows (list[BookMoveRow]): The line's moves.
        final_epd (str): The position after the last move.

    Returns:
        tuple[dict[str, tuple[BookMove, ...]], frozenset[str]]: Position -> moves, and every
            position on the line, including the final one.
    """
    by_position: dict[str, dict[str, str]] = {}
    for row in rows:
        by_position.setdefault(row.epd_before, {})[row.uci] = row.san
    moves = {
        epd: tuple(BookMove(uci, san) for uci, san in by_uci.items())
        for epd, by_uci in by_position.items()
    }
    return moves, frozenset(moves) | {final_epd}
