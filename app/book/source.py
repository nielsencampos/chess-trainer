"""Reads openings/<group>/[others/]<family>.json, the source of the book. Problems fail loudly."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import chess

from app.book.models import BookError, BookMoveRow

GROUPS = ("kings-pawn", "queens-pawn", "flank", "others")


@dataclass(frozen=True)
class OpeningLine:
    """A line as written in an opening file.

    Attributes:
        line_id (str): The line id, which never changes.
        names (dict[str, str]): The line's name by locale.
        eco (str | None): The ECO code, if given.
        opening (str | None): The catalog name of the final position, if given.
        source (str): Where the line came from.
        moves (tuple[str, ...]): The moves in SAN.
        subgroup (dict[str, str] | None): The subgroup's name by locale, or None for a loose line.
    """

    line_id: str
    names: dict[str, str]
    eco: str | None
    opening: str | None
    source: str
    moves: tuple[str, ...]
    subgroup: dict[str, str] | None = None


@dataclass(frozen=True)
class OpeningFile:
    """One opening file: a family and its lines.

    Attributes:
        family_id (str): The family id, equal to the file name.
        names (dict[str, str]): The family's name by locale.
        lines (tuple[OpeningLine, ...]): Its lines, subgroups first, then the loose ones.
        file_name (str): The path relative to `openings/`.
        file_hash (str): SHA-256 of the file, to reload only what changed.
        group (str): The group folder, such as `kings-pawn`.
        order (int | None): The family's place in its group, or None for "Others".
    """

    family_id: str
    names: dict[str, str]
    lines: tuple[OpeningLine, ...]
    file_name: str
    file_hash: str
    group: str = "others"
    order: int | None = None


@dataclass(frozen=True)
class ReplayedLine:
    """A line played on a board.

    Attributes:
        rows (list[BookMoveRow]): One row per move.
        final_epd (str): The position after the last move.
        pgn (str): The moves as PGN movetext, with normalized SAN.
    """

    rows: list[BookMoveRow]
    final_epd: str
    pgn: str


def _names(value: object, where: str) -> dict[str, str]:
    """Checks a `names` object.

    Args:
        value (object): The raw `names` value.
        where (str): Where it is, for the error message.

    Returns:
        dict[str, str]: The names by locale.

    Raises:
        BookError: It is not an object with a non-empty `en`.
    """
    if not isinstance(value, dict) or not value.get("en"):
        raise BookError(f"{where}: names must include a non-empty 'en'")
    return value


def _parse_line(raw: object, where: str, subgroup: dict[str, str] | None = None) -> OpeningLine:
    """Checks and reads one line object.

    Args:
        raw (object): The raw line.
        where (str): Where it is, for error messages.
        subgroup (dict[str, str] | None): The names of its subgroup, if it is in one.

    Returns:
        OpeningLine: The line.

    Raises:
        BookError: The id, moves or source is missing or malformed.
    """
    if not isinstance(raw, dict):
        raise BookError(f"{where}: a line must be an object")
    line_id = raw.get("id")
    if not line_id or not isinstance(line_id, str):
        raise BookError(f"{where}: a line has no 'id'")
    where = f"{where}/{line_id}"
    moves = raw.get("moves")
    if not isinstance(moves, list) or not moves or not all(isinstance(m, str) for m in moves):
        raise BookError(f"{where}: 'moves' must be a non-empty list of SAN strings")
    source = raw.get("source")
    if not source or not isinstance(source, str):
        raise BookError(f"{where}: a line has no 'source'")
    return OpeningLine(
        line_id=line_id,
        names=_names(raw.get("names"), where),
        eco=raw.get("eco"),
        opening=raw.get("opening"),
        source=source,
        moves=tuple(moves),
        subgroup=subgroup,
    )


def _parse_lines(raw: dict, where: str) -> tuple[OpeningLine, ...]:
    """Reads a family's lines: those in its variants first, then the loose ones ("Others").

    Args:
        raw (dict): The family object.
        where (str): The file name, for error messages.

    Returns:
        tuple[OpeningLine, ...]: The lines.

    Raises:
        BookError: The family has no lines, or a variant or line is malformed.
    """
    variants = raw.get("variants", [])
    loose = raw.get("lines", [])
    if not isinstance(variants, list) or not isinstance(loose, list) or not (variants or loose):
        raise BookError(f"{where}: 'lines' must be a non-empty list")
    lines: list[OpeningLine] = []
    for variant in variants:
        if not isinstance(variant, dict) or not variant.get("lines"):
            raise BookError(f"{where}: a variant must have 'lines'")
        names = _names(variant.get("names"), where)
        lines.extend(_parse_line(item, where, names) for item in variant["lines"])
    lines.extend(_parse_line(item, where) for item in loose)
    return tuple(lines)


def read_opening_files(directory: Path) -> list[OpeningFile]:
    """Reads every opening file, checking structure and uniqueness across all of them.

    Legality of the moves is checked by `replay`.

    Args:
        directory (Path): The `openings/` folder.

    Returns:
        list[OpeningFile]: The files, sorted by path.

    Raises:
        BookError: There are no files, a file is malformed, or two lines share an id or moves.
    """
    paths = sorted(directory.rglob("*.json"))
    if not paths:
        raise BookError(f"no opening files in {directory}")

    files: list[OpeningFile] = []
    seen_ids: dict[str, str] = {}
    seen_moves: dict[tuple[str, ...], str] = {}
    for path in paths:
        content = path.read_bytes()
        try:
            raw = json.loads(content)
        except ValueError as error:
            raise BookError(f"{path.name}: invalid JSON: {error}") from error
        if not isinstance(raw, dict):
            raise BookError(f"{path.name}: must be an object")
        family_id = raw.get("id")
        if family_id != path.stem:
            raise BookError(f"{path.name}: 'id' must match the file name, got {family_id!r}")
        relative = path.relative_to(directory)
        group = relative.parts[0] if len(relative.parts) > 1 else "others"
        if group not in GROUPS:
            raise BookError(f"{relative}: unknown group {group!r}, expected one of {GROUPS}")
        order = raw.get("order")
        if order is not None and not isinstance(order, int):
            raise BookError(f"{path.name}: 'order' must be a number or null")

        lines = _parse_lines(raw, path.name)
        for line in lines:
            if line.line_id in seen_ids:
                raise BookError(
                    f"{path.name}: duplicate line id {line.line_id!r}, "
                    f"also in {seen_ids[line.line_id]}"
                )
            seen_ids[line.line_id] = path.name
            if line.moves in seen_moves:
                raise BookError(
                    f"{path.name}/{line.line_id}: same moves as {seen_moves[line.moves]}"
                )
            seen_moves[line.moves] = line.line_id
        files.append(
            OpeningFile(
                family_id=family_id,
                names=_names(raw.get("names"), path.name),
                lines=lines,
                file_name=str(relative),
                group=group,
                order=order,
                file_hash=hashlib.sha256(content).hexdigest(),
            )
        )
    return files


def replay(line: OpeningLine) -> ReplayedLine:
    """Plays a line's moves from the starting position.

    Args:
        line (OpeningLine): The line.

    Returns:
        ReplayedLine: Its rows, final position and PGN.

    Raises:
        BookError: A move is illegal.
    """
    board = chess.Board()
    rows: list[BookMoveRow] = []
    parts: list[str] = []
    for ply, san in enumerate(line.moves, start=1):
        epd = board.epd()
        try:
            move = board.parse_san(san)
        except ValueError as error:
            raise BookError(f"{line.line_id}: illegal move {san!r} at ply {ply}") from error
        normalized = board.san(move)
        if ply % 2 == 1:
            parts.append(f"{(ply + 1) // 2}.")
        parts.append(normalized)
        rows.append(BookMoveRow(epd, ply, move.uci(), normalized))
        board.push(move)
    return ReplayedLine(rows=rows, final_epd=board.epd(), pgn=" ".join(parts))
