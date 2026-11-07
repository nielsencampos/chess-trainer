"""Read the vendored catalog and index it by final position."""

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import chess.pgn

DATA_DIR = Path(__file__).parent / "data"
SOURCE_COMMIT_FILE = Path(__file__).parent / "SOURCE_COMMIT"


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    eco: str
    name: str
    pgn: str
    epd: str


def source_commit() -> str:
    return SOURCE_COMMIT_FILE.read_text(encoding="utf-8").strip()


def final_epd(pgn: str) -> str:
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None or game.errors:
        raise ValueError(f"invalid catalog PGN: {pgn!r}")
    return game.end().board().epd()


def load_catalog(data_dir: Path = DATA_DIR) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    for path in sorted(data_dir.glob("*.tsv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                entries.append(
                    CatalogEntry(row["eco"], row["name"], row["pgn"], final_epd(row["pgn"]))
                )
    return entries


def index_by_position(entries: list[CatalogEntry]) -> dict[str, list[CatalogEntry]]:
    index: dict[str, list[CatalogEntry]] = defaultdict(list)
    for entry in entries:
        index[entry.epd].append(entry)
    return dict(index)
