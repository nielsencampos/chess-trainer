"""Reads openings/<family>.json, the source of the book. Any problem fails loudly."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import chess

from app.book.models import BookError, BookMoveRow


@dataclass(frozen=True)
class OpeningLine:
    line_id: str
    names: dict[str, str]
    eco: str | None
    opening: str | None
    source: str
    moves: tuple[str, ...]


@dataclass(frozen=True)
class OpeningFile:
    family_id: str
    names: dict[str, str]
    lines: tuple[OpeningLine, ...]
    file_name: str
    file_hash: str


@dataclass(frozen=True)
class ReplayedLine:
    rows: list[BookMoveRow]
    final_epd: str
    pgn: str


def _names(value: object, where: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value.get("en"):
        raise BookError(f"{where}: names must include a non-empty 'en'")
    return value


def _parse_line(raw: object, where: str) -> OpeningLine:
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
    )


def read_opening_files(directory: Path) -> list[OpeningFile]:
    """Checks structure and uniqueness across all files. Legality is checked by `replay`."""
    paths = sorted(directory.glob("*.json"))
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
        raw_lines = raw.get("lines")
        if not isinstance(raw_lines, list) or not raw_lines:
            raise BookError(f"{path.name}: 'lines' must be a non-empty list")

        lines = tuple(_parse_line(item, path.name) for item in raw_lines)
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
                file_name=path.name,
                file_hash=hashlib.sha256(content).hexdigest(),
            )
        )
    return files


def replay(line: OpeningLine) -> ReplayedLine:
    """Plays the moves from the start. An illegal move raises BookError."""
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
