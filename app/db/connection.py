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
    """Opens the DuckDB file, creating its folder if needed.

    Args:
        path (Path): The database file.

    Returns:
        duckdb.DuckDBPyConnection: The one connection of this process.

    Raises:
        DatabaseError: The file cannot be opened, such as when another process holds it.
    """
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
    """Applies pending migrations, each in its own transaction.

    Args:
        connection (duckdb.DuckDBPyConnection): The database.
        directory (Path): The folder of numbered `NNN_name.sql` files.

    Returns:
        list[int]: The versions applied by this call, in order.

    Raises:
        DatabaseError: A file name is not numbered, or a migration fails (it is rolled back).
    """
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
