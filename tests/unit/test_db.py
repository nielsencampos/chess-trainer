"""The database: migrations, loading `openings/`, and the committed book against the catalog."""

import json

import chess
import pytest

from app.book.models import BookError
from app.book.source import read_opening_files
from app.book.sync import load_book, sync_catalog, sync_openings
from app.config import Settings
from app.db.connection import DatabaseError, apply_migrations, open_database
from catalog.generate_openings import line_id_of, render
from catalog.loader import index_by_position, load_catalog, source_commit
from catalog.validate import name_coverage, validate

SETTINGS = Settings()


def line(line_id, moves, name="Line", **extra):
    """A line object for a test opening file.

    Args:
        line_id (str): The line id.
        moves (list[str]): The SAN moves.
        name (str): The English name.
        **extra (object): Other fields, such as `eco` or `opening`.

    Returns:
        dict: The line.
    """
    return {
        "id": line_id,
        "names": {"en": name},
        "moves": moves,
        "source": "test",
        **extra,
    }


def write_family(directory, family_id, *lines, name="Family"):
    """Writes a test opening file.

    Args:
        directory (Path): The `openings/` folder.
        family_id (str): The family id and file name.
        *lines (dict): The family's lines.
        name (str): The family's English name.
    """
    document = {"id": family_id, "names": {"en": name}, "lines": list(lines)}
    (directory / f"{family_id}.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def connection(tmp_path):
    """An empty, migrated database.

    Args:
        tmp_path (Path): The test's temporary folder.

    Yields:
        duckdb.DuckDBPyConnection: The database, closed after the test.
    """
    database = open_database(tmp_path / "new" / "test.duckdb")
    apply_migrations(database)
    yield database
    database.close()


@pytest.fixture
def openings(tmp_path):
    """A small `openings/` folder: a Caro-Kann family with two lines and a Vienna one.

    Args:
        tmp_path (Path): The test's temporary folder.

    Returns:
        Path: The folder.
    """
    directory = tmp_path / "openings"
    directory.mkdir()
    write_family(
        directory,
        "caro",
        line("c1", ["e4", "c6"], eco="B10", opening="Caro-Kann Defense"),
        line("c2", ["e4", "c6", "d4", "d5", "e5"], name="Advance", eco="B12"),
        name="Caro-Kann Defense",
    )
    write_family(directory, "vienna", line("v1", ["e4", "e5", "Nc3"]), name="Vienna Game")
    return directory


def count(database, table, where="true"):
    """Counts rows of a table.

    Args:
        database (duckdb.DuckDBPyConnection): The database.
        table (str): The table.
        where (str): An SQL condition.

    Returns:
        int: The count.
    """
    return database.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()[0]


# --- Migrations and connection ---


def test_migrations_apply_once(tmp_path):
    """Migrations apply once.

    Args:
        tmp_path (Path): A temporary folder for this test.
    """
    database = open_database(tmp_path / "test.duckdb")
    assert apply_migrations(database) == [1, 2, 3, 4, 5]
    assert apply_migrations(database) == []
    assert count(database, "schema_migrations") == 5
    database.close()


def test_failed_migration_rolls_back_and_fails_loudly(tmp_path):
    """Failed migration rolls back and fails loudly.

    Args:
        tmp_path (Path): A temporary folder for this test.
    """
    database = open_database(tmp_path / "test.duckdb")
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "001_bad.sql").write_text("CREATE TABLE t (a INT); SELECT nope;", encoding="utf-8")
    with pytest.raises(DatabaseError, match="001_bad"):
        apply_migrations(database, directory)
    assert count(database, "schema_migrations") == 0
    assert ("t",) not in database.execute("SELECT table_name FROM duckdb_tables()").fetchall()
    database.close()


def test_bad_migration_file_name_fails(tmp_path):
    """Bad migration file name fails.

    Args:
        tmp_path (Path): A temporary folder for this test.
    """
    database = open_database(tmp_path / "test.duckdb")
    directory = tmp_path / "migrations"
    directory.mkdir()
    (directory / "1_bad.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(DatabaseError, match="bad migration file name"):
        apply_migrations(database, directory)
    database.close()


def test_unusable_path_fails_with_a_helpful_message(tmp_path):
    """Unusable path fails with a helpful message.

    Args:
        tmp_path (Path): A temporary folder for this test.
    """
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(DatabaseError, match="UID 1000"):
        open_database(blocker / "db" / "test.duckdb")


# --- Opening files ---


def test_sync_fills_the_tables(connection, openings):
    """Sync fills the tables.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    assert sync_openings(connection, openings) == ["caro", "vienna"]
    assert count(connection, "variants") == 3
    assert count(connection, "repertoires", "source = 'repo'") == 2
    assert count(connection, "book_moves") == 2 + 5 + 3
    row = connection.execute("SELECT pgn, moves_san FROM variants WHERE variant_id='v1'").fetchone()
    assert row == ("1. e4 e5 2. Nc3", ["e4", "e5", "Nc3"])


def test_only_changed_files_reload(connection, openings):
    """Only changed files reload.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    sync_openings(connection, openings)
    assert sync_openings(connection, openings) == []

    write_family(openings, "vienna", line("v1", ["e4", "e5", "Nc3", "Nf6"]), name="Vienna Game")
    assert sync_openings(connection, openings) == ["vienna"]
    assert count(connection, "book_moves", "variant_id = 'v1'") == 4
    assert count(connection, "book_moves", "variant_id = 'c1'") == 2


def test_extended_line_keeps_its_id(connection, openings):
    """Extended line keeps its id.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    sync_openings(connection, openings)
    write_family(openings, "vienna", line("v1", ["e4", "e5", "Nc3", "Nf6"]), name="Vienna Game")
    sync_openings(connection, openings)
    book = load_book(connection)
    assert book.variants["v1"].pgn == "1. e4 e5 2. Nc3 Nf6"


def test_removed_line_becomes_inactive_and_stays_in_the_table(connection, openings):
    """Removed line becomes inactive and stays in the table.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    sync_openings(connection, openings)
    write_family(openings, "caro", line("c1", ["e4", "c6"]), name="Caro-Kann Defense")
    sync_openings(connection, openings)
    assert count(connection, "variants", "variant_id = 'c2' AND NOT active") == 1
    assert count(connection, "book_moves", "variant_id = 'c2'") == 0
    assert "c2" not in load_book(connection).variants


def test_removed_file_deactivates_its_lines(connection, openings):
    """Removed file deactivates its lines.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    sync_openings(connection, openings)
    (openings / "vienna.json").unlink()
    assert sync_openings(connection, openings) == []
    assert count(connection, "variants", "variant_id = 'v1' AND NOT active") == 1
    assert set(load_book(connection).repertoires) == {"caro"}


def test_line_moved_between_files_stays_active(connection, openings):
    """Line moved between files stays active.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    sync_openings(connection, openings)
    write_family(openings, "caro", line("c1", ["e4", "c6"]), name="Caro-Kann Defense")
    write_family(
        openings,
        "vienna",
        line("v1", ["e4", "e5", "Nc3"]),
        line("c2", ["e4", "c6", "d4", "d5", "e5"], name="Advance"),
        name="Vienna Game",
    )
    sync_openings(connection, openings)
    book = load_book(connection)
    assert book.variants["c2"].repertoire_id == "vienna"


def test_imported_families_survive_a_sync(connection, openings):
    """Imported families survive a sync.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    sync_openings(connection, openings)
    connection.execute(
        "INSERT INTO repertoires (repertoire_id, source, loaded_at) VALUES ('mine', 'user', now())"
    )
    connection.execute(
        "INSERT INTO variants "
        "(variant_id, repertoire_id, pgn, moves_san, final_epd, source, active) "
        "VALUES ('m1','mine','1. d4',['d4'],'x','me',true)"
    )
    (openings / "vienna.json").unlink()
    sync_openings(connection, openings)
    assert count(connection, "variants", "variant_id = 'm1' AND active") == 1
    assert count(connection, "repertoires", "repertoire_id = 'mine'") == 1


def test_database_survives_reopening(tmp_path, openings):
    """Database survives reopening.

    Args:
        tmp_path (Path): A temporary folder for this test.
        openings (Path): A small `openings/` folder with two families.
    """
    path = tmp_path / "test.duckdb"
    database = open_database(path)
    apply_migrations(database)
    sync_openings(database, openings)
    database.close()
    reopened = open_database(path)
    assert apply_migrations(reopened) == []
    assert sync_openings(reopened, openings) == []
    assert len(load_book(reopened).variants) == 3
    reopened.close()


def test_book_read_from_the_database(connection, openings):
    """Book read from the database.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    sync_openings(connection, openings)
    book = load_book(connection)
    assert book.repertoires["caro"].names == {"en": "Caro-Kann Defense"}
    assert len(book.repertoires["caro"].variant_ids) == 2
    variant = book.variants["c2"]
    assert variant.eco == "B12"
    assert variant.names == {"en": "Advance"}
    assert [move.san for move in variant.moves[chess.Board().epd()]] == ["e4"]
    assert variant.final_epd in variant.positions
    assert variant.final_epd not in variant.moves


def test_translated_names_load(connection, tmp_path):
    """Translated names load.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        tmp_path (Path): A temporary folder for this test.
    """
    directory = tmp_path / "translated"
    directory.mkdir()
    document = {
        "id": "x",
        "names": {"en": "X", "pt-BR": "Xis"},
        "lines": [{**line("x1", ["e4"]), "names": {"en": "L", "pt-BR": "Linha"}}],
    }
    (directory / "x.json").write_text(json.dumps(document), encoding="utf-8")
    sync_openings(connection, directory)
    book = load_book(connection)
    assert book.repertoires["x"].names["pt-BR"] == "Xis"
    assert book.variants["x1"].names["pt-BR"] == "Linha"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not json", "invalid JSON"),
        ('{"id": "other", "names": {"en": "X"}, "lines": []}', "match the file name"),
        ('{"id": "bad", "names": {"en": "X"}, "lines": []}', "non-empty list"),
        (json.dumps({"id": "bad", "names": {}, "lines": [line("a", ["e4"])]}), "'en'"),
        (
            json.dumps(
                {"id": "bad", "names": {"en": "X"}, "lines": [{"id": "a", "moves": ["e4"]}]}
            ),
            "'source'",
        ),
        (json.dumps({"id": "bad", "names": {"en": "X"}, "lines": [line("a", [])]}), "'moves'"),
    ],
)
def test_invalid_file_fails_loudly(connection, tmp_path, content, message):
    """Invalid file fails loudly.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        tmp_path (Path): A temporary folder for this test.
        content (str): The content of a bad opening file.
        message (str): Part of the expected error message.
    """
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / "bad.json").write_text(content, encoding="utf-8")
    with pytest.raises(BookError, match=message):
        sync_openings(connection, directory)


def test_illegal_move_fails_and_changes_nothing(connection, openings):
    """Illegal move fails and changes nothing.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    sync_openings(connection, openings)
    write_family(openings, "vienna", line("v1", ["e4", "e4"]), name="Vienna Game")
    with pytest.raises(BookError, match="illegal move"):
        sync_openings(connection, openings)
    assert count(connection, "book_moves", "variant_id = 'v1'") == 3


def test_duplicate_id_across_files_fails(connection, openings):
    """Duplicate id across files fails.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    write_family(openings, "other", line("v1", ["d4"]))
    with pytest.raises(BookError, match="duplicate line id"):
        sync_openings(connection, openings)


def test_duplicate_moves_fail(connection, openings):
    """Duplicate moves fail.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        openings (Path): A small `openings/` folder with two families.
    """
    write_family(openings, "other", line("o1", ["e4", "e5", "Nc3"]))
    with pytest.raises(BookError, match="same moves"):
        sync_openings(connection, openings)


def test_empty_directory_and_empty_book_fail(connection, tmp_path):
    """Empty directory and empty book fail.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        tmp_path (Path): A temporary folder for this test.
    """
    with pytest.raises(BookError, match="no opening files"):
        sync_openings(connection, tmp_path)
    with pytest.raises(BookError, match="empty"):
        load_book(connection)


def test_groups_come_from_the_folders_and_subgroups_load(connection, tmp_path):
    """Groups come from the folders and subgroups load.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        tmp_path (Path): A temporary folder for this test.
    """
    directory = tmp_path / "tree"
    (directory / "kings-pawn" / "others").mkdir(parents=True)
    document = {
        "id": "x",
        "names": {"en": "X"},
        "order": 2,
        "variants": [{"names": {"en": "V", "es": "Ve"}, "lines": [line("a", ["e4", "c5"])]}],
        "lines": [line("b", ["e4", "c6"])],
    }
    (directory / "kings-pawn" / "x.json").write_text(json.dumps(document), encoding="utf-8")
    rare = {"id": "y", "names": {"en": "Y"}, "order": None, "lines": [line("c", ["e4", "e5"])]}
    (directory / "kings-pawn" / "others" / "y.json").write_text(json.dumps(rare), encoding="utf-8")
    sync_openings(connection, directory)
    book = load_book(connection)
    assert (book.repertoires["x"].group, book.repertoires["x"].order) == ("kings-pawn", 2)
    assert (book.repertoires["y"].group, book.repertoires["y"].order) == ("kings-pawn", None)
    assert book.variants["a"].subgroup == {"en": "V", "es": "Ve"}
    assert book.variants["b"].subgroup is None


def test_unknown_group_folder_fails(connection, tmp_path):
    """Unknown group folder fails.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
        tmp_path (Path): A temporary folder for this test.
    """
    directory = tmp_path / "tree"
    (directory / "nope").mkdir(parents=True)
    document = {"id": "x", "names": {"en": "X"}, "lines": [line("a", ["e4"])]}
    (directory / "nope" / "x.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(BookError, match="unknown group"):
        sync_openings(connection, directory)


# --- Committed files and reference catalog ---


@pytest.fixture(scope="module")
def committed():
    """The opening files in the repository, read once per module.

    Returns:
        list[OpeningFile]: The files.
    """
    return read_opening_files(SETTINGS.openings_dir)


@pytest.fixture(scope="module")
def catalog():
    """The vendored catalog, read once per module.

    Returns:
        list[CatalogEntry]: The entries.
    """
    return load_catalog()


def test_catalog_is_complete(catalog):
    """Catalog is complete.

    Args:
        catalog (list[CatalogEntry]): The vendored catalog.
    """
    assert len(catalog) == 3865
    assert sum(entry.name.startswith("Caro-Kann") for entry in catalog) == 110
    assert len(source_commit()) == 40


def test_committed_openings_cover_the_catalog(committed, catalog):
    """Committed openings cover the catalog.

    Args:
        committed (list[OpeningFile]): The opening files in the repository.
        catalog (list[CatalogEntry]): The vendored catalog.
    """
    assert len(committed) == 122
    assert sum(len(item.lines) for item in committed) == 3865
    by_id = {line.line_id for item in committed for line in item.lines}
    assert by_id == {line_id_of(entry.pgn) for entry in catalog}


def test_committed_openings_match_the_catalog(committed, catalog):
    """Committed openings match the catalog.

    Args:
        committed (list[OpeningFile]): The opening files in the repository.
        catalog (list[CatalogEntry]): The vendored catalog.
    """
    assert validate(committed, index_by_position(catalog)) == []


def test_validator_detects_a_wrong_name(tmp_path, catalog):
    """Validator detects a wrong name.

    Args:
        tmp_path (Path): A temporary folder for this test.
        catalog (list[CatalogEntry]): The vendored catalog.
    """
    write_family(tmp_path, "x", line("x1", ["e4", "c6"], opening="Made Up", eco="B10"))
    problems = validate(read_opening_files(tmp_path), index_by_position(catalog))
    assert "Made Up" in problems[0]


def test_validator_accepts_our_own_lines_without_a_catalog_name(tmp_path, catalog):
    """Validator accepts our own lines without a catalog name.

    Args:
        tmp_path (Path): A temporary folder for this test.
        catalog (list[CatalogEntry]): The vendored catalog.
    """
    write_family(tmp_path, "x", line("x1", ["e4", "c6", "d4", "d5", "e5", "Bf5", "Nf3", "e6"]))
    assert validate(read_opening_files(tmp_path), index_by_position(catalog)) == []


def test_every_name_has_english_and_coverage_is_measured(committed):
    """Every name has English and coverage is measured.

    Args:
        committed (list[OpeningFile]): The opening files in the repository.
    """
    coverage = name_coverage(committed)
    assert coverage["en"]["lines"] == (3865, 3865)
    assert coverage["en"]["families"] == (122, 122)
    for locale in ("pt-BR", "es"):
        assert coverage[locale]["lines"][0] > 0
        assert coverage[locale]["families"][0] > 0


def test_every_vienna_line_starts_with_the_vienna(committed):
    """Every Vienna line starts with the Vienna.

    Args:
        committed (list[OpeningFile]): The opening files in the repository.
    """
    vienna = next(item for item in committed if item.family_id == "vienna-game")
    assert len(vienna.lines) == 59
    assert all(line.moves[:3] == ("e4", "e5", "Nc3") for line in vienna.lines)


def test_fragmented_families_stay_merged(committed):
    """Fragmented families stay merged.

    Args:
        committed (list[OpeningFile]): The opening files in the repository.
    """
    families = {item.family_id for item in committed}
    assert "king-s-gambit" in families
    assert not families & {
        "king-s-gambit-accepted",
        "queen-s-gambit-declined",
        "vienna-gambit-with-max-lange-defense",
        "london-system-with-bd3",
    }


def test_committed_sources_name_the_catalog_commit(committed):
    """Committed sources name the catalog commit.

    Args:
        committed (list[OpeningFile]): The opening files in the repository.
    """
    short = source_commit()[:7]
    assert all(short in line.source for item in committed for line in item.lines)


def test_files_keep_move_lists_on_one_line():
    """Files keep move lists on one line."""
    text = render({"id": "x", "lines": [{"moves": ["e4", "c6"]}]})
    assert '"moves": ["e4", "c6"]' in text
    assert json.loads(text)["lines"][0]["moves"] == ["e4", "c6"]


def test_catalog_sync_is_idempotent(connection):
    """Catalog sync is idempotent.

    Args:
        connection (duckdb.DuckDBPyConnection): An empty, migrated database.
    """
    assert sync_catalog(connection, SETTINGS.catalog_dir) is True
    assert sync_catalog(connection, SETTINGS.catalog_dir) is False
    assert count(connection, "openings_catalog") == 3865
    assert count(connection, "catalog_loads") == 1


def test_full_book_loads(loaded_database):
    """The whole book loads: 3,865 lines in 122 families.

    Args:
        loaded_database (Path): The session's database with the book loaded.
    """
    database = open_database(loaded_database)
    book = load_book(database)
    assert len(book.variants) == 3865
    assert len(book.repertoires) == 122
    database.close()
