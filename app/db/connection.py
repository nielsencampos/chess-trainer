"""One DuckDB connection per process (brief §7). Migrations are applied in version order."""

import re
from datetime import UTC, datetime
from pathlib import Path

import duckdb

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


class DatabaseError(RuntimeError):
    """The database cannot be used and the app must not start."""


def open_database(path: Path) -> duckdb.DuckDBPyConnection:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(path))
    except (OSError, duckdb.Error) as error:
        raise DatabaseError(
            f"cannot open {path}: {error}. In Docker, ./data must be writable by UID 1000 "
            "and no other process may have the file open."
        ) from error


def apply_migrations(
    connection: duckdb.DuckDBPyConnection, directory: Path = MIGRATIONS_DIR
) -> list[int]:
    """Applies pending migrations, each in its own transaction. Returns the versions applied."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, name VARCHAR NOT NULL, applied_at TIMESTAMPTZ NOT NULL)"
    )
    done = {
        row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    applied = []
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_NAME.match(path.name)
        if match is None:
            raise DatabaseError(f"bad migration file name: {path.name}")
        version = int(match.group(1))
        if version in done:
            continue
        connection.begin()
        try:
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                [version, path.name, datetime.now(UTC)],
            )
            connection.commit()
        except duckdb.Error as error:
            connection.rollback()
            raise DatabaseError(f"migration {path.name} failed: {error}") from error
        applied.append(version)
    return applied
