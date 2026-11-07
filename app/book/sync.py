"""Loads openings/ and the reference catalog into DuckDB, and reads the book back from there."""

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from app.book.models import Book, BookError, BookMoveRow, Repertoire, Variant, index_moves
from app.book.source import read_opening_files, replay
from catalog.loader import load_catalog, source_commit

BATCH_ROWS = 1000
REPO_SOURCE = "repo"


def _insert_many(
    connection: duckdb.DuckDBPyConnection, statement: str, width: int, rows: list[tuple]
) -> None:
    """`statement` ends in VALUES. Multi-row inserts: executemany is far slower in DuckDB."""
    row_sql = "(" + ",".join("?" * width) + ")"
    for start in range(0, len(rows), BATCH_ROWS):
        batch = rows[start : start + BATCH_ROWS]
        sql = f"{statement} {','.join([row_sql] * len(batch))}"
        connection.execute(sql, [value for row in batch for value in row])


def sync_openings(connection: duckdb.DuckDBPyConnection, directory: Path) -> list[str]:
    """Reloads only the files that changed. Returns their family ids.

    Rows are never deleted from `variants`: a line that disappears becomes inactive, because
    statistics are keyed on its id. Families from other sources (`user`) are never touched.
    """
    files = read_opening_files(directory)
    known = dict(
        connection.execute(
            "SELECT repertoire_id, file_hash FROM repertoires WHERE source = ?", [REPO_SOURCE]
        ).fetchall()
    )
    present = {opening_file.family_id for opening_file in files}
    removed = [family_id for family_id in known if family_id not in present]
    changed = [item for item in files if known.get(item.family_id) != item.file_hash]
    if not changed and not removed:
        return []

    now = datetime.now(UTC)
    repertoire_rows, variant_rows, move_rows, name_rows = [], [], [], []
    for opening_file in changed:
        family_id = opening_file.family_id
        repertoire_rows.append(
            (family_id, REPO_SOURCE, opening_file.file_name, opening_file.file_hash, now)
        )
        name_rows.extend(
            ("repertoire", family_id, locale, name) for locale, name in opening_file.names.items()
        )
        for line in opening_file.lines:
            replayed = replay(line)
            variant_rows.append(
                (
                    line.line_id,
                    family_id,
                    line.eco,
                    line.opening,
                    replayed.pgn,
                    [row.san for row in replayed.rows],
                    replayed.final_epd,
                    line.source,
                    True,
                )
            )
            move_rows.extend(
                (family_id, line.line_id, row.epd_before, row.ply, row.uci, row.san)
                for row in replayed.rows
            )
            name_rows.extend(
                ("variant", line.line_id, locale, name) for locale, name in line.names.items()
            )

    connection.begin()
    try:
        # Deactivate first: a line moved between two changed files must end up active.
        for family_id in [*removed, *(item.family_id for item in changed)]:
            connection.execute("DELETE FROM book_moves WHERE repertoire_id = ?", [family_id])
            connection.execute(
                "UPDATE variants SET active = false WHERE repertoire_id = ?", [family_id]
            )
        for family_id in removed:
            connection.execute("DELETE FROM repertoires WHERE repertoire_id = ?", [family_id])
        _insert_many(connection, "INSERT OR REPLACE INTO repertoires VALUES", 5, repertoire_rows)
        _insert_many(connection, "INSERT OR REPLACE INTO variants VALUES", 9, variant_rows)
        _insert_many(connection, "INSERT OR REPLACE INTO names VALUES", 4, name_rows)
        _insert_many(connection, "INSERT INTO book_moves VALUES", 6, move_rows)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return [item.family_id for item in changed]


def catalog_hash(data_dir: Path) -> str:
    digest = hashlib.sha256()
    paths = sorted(data_dir.glob("*.tsv"))
    if not paths:
        raise BookError(f"no catalog files in {data_dir}")
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def sync_catalog(connection: duckdb.DuckDBPyConnection, data_dir: Path) -> bool:
    """Loads the reference catalog when it changed. The bot does not play from this table."""
    content_hash = catalog_hash(data_dir)
    last = connection.execute(
        "SELECT content_hash FROM catalog_loads ORDER BY loaded_at DESC LIMIT 1"
    ).fetchone()
    if last is not None and last[0] == content_hash:
        return False
    commit = source_commit()
    rows = [
        (entry.eco, entry.name, entry.pgn, entry.epd, commit) for entry in load_catalog(data_dir)
    ]
    connection.begin()
    try:
        connection.execute("DELETE FROM openings_catalog")
        _insert_many(connection, "INSERT INTO openings_catalog VALUES", 5, rows)
        connection.execute(
            "INSERT INTO catalog_loads VALUES (?, ?, ?)", [content_hash, commit, datetime.now(UTC)]
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return True


def _names(connection: duckdb.DuckDBPyConnection, entity_type: str) -> dict[str, dict[str, str]]:
    names: dict[str, dict[str, str]] = defaultdict(dict)
    for entity_id, locale, name in connection.execute(
        "SELECT entity_id, locale, name FROM names WHERE entity_type = ?", [entity_type]
    ).fetchall():
        names[entity_id][locale] = name
    return names


def load_book(connection: duckdb.DuckDBPyConnection) -> Book:
    """The app reads the book only from the database (brief §6)."""
    moves: dict[str, list[BookMoveRow]] = defaultdict(list)
    for variant_id, epd_before, ply, uci, san in connection.execute(
        "SELECT variant_id, epd_before, ply, uci, san FROM book_moves ORDER BY variant_id, ply"
    ).fetchall():
        moves[variant_id].append(BookMoveRow(epd_before, ply, uci, san))

    variant_names = _names(connection, "variant")
    repertoire_names = _names(connection, "repertoire")
    variants: dict[str, Variant] = {}
    members: dict[str, list[str]] = defaultdict(list)
    for variant_id, repertoire_id, eco, opening, pgn, final_epd, source in connection.execute(
        "SELECT variant_id, repertoire_id, eco, opening, pgn, final_epd, source FROM variants "
        "WHERE active ORDER BY repertoire_id, pgn"
    ).fetchall():
        book_moves, positions = index_moves(moves[variant_id], final_epd)
        variants[variant_id] = Variant(
            variant_id=variant_id,
            repertoire_id=repertoire_id,
            names=variant_names[variant_id],
            eco=eco,
            opening=opening,
            source=source,
            pgn=pgn,
            moves=book_moves,
            positions=positions,
            final_epd=final_epd,
        )
        members[repertoire_id].append(variant_id)
    if not variants:
        raise BookError("the book is empty")
    repertoires = {
        key: Repertoire(key, repertoire_names[key], tuple(ids)) for key, ids in members.items()
    }
    return Book(repertoires=repertoires, variants=variants)
