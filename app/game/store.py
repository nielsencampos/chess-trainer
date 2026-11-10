"""Saves games to DuckDB on every move and rebuilds an unfinished one from its row."""

import json
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime

import chess
import duckdb

from app import __version__
from app.book.models import Book, BookMoveRow, Variant, index_moves
from app.game.imports import ImportedGame, annotation_count_of, content_hash
from app.game.pace import TIME_CONTROLS
from app.game.session import (
    CHESS960_PREFIX,
    BotDeviationSetup,
    Deviation,
    GameResult,
    GameSession,
    MoveRecord,
    Selection,
    chess960_line,
)

GAME_LINE_PREFIX = "game:"


# Columns of `games`, in table order, after every migration.
GAME_COLUMNS = 29


class GameStore:
    """Reads and writes the `games` table, one cursor per call."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        """Creates the store.

        Args:
            connection (duckdb.DuckDBPyConnection): The database.
        """
        self._connection = connection

    def save(self, session: GameSession) -> None:
        """Writes a game's whole row, replacing the previous one: called after every move.

        Args:
            session (GameSession): The game.
        """
        eco, opening = session.opening or (session.variant.eco, session.variant.opening)
        white, black = session.players()
        self._connection.cursor().execute(
            f"INSERT OR REPLACE INTO games VALUES ({', '.join('?' * GAME_COLUMNS)})",
            [
                session.game_id,
                "finished" if session.is_over else "active",
                session.started_at.replace(tzinfo=None),
                datetime.now(UTC).replace(tzinfo=None) if session.is_over else None,
                "white" if session.user_color == chess.WHITE else "black",
                session.time_control_key,
                session.level,
                session.pace,
                [variant.variant_id for variant in session.selection.variants],
                session.variant.variant_id,
                session.outcome.result if session.outcome else None,
                session.outcome.termination if session.outcome else None,
                session.in_theory,
                session.theory_until_ply,
                json.dumps([asdict(record) for record in session.moves]),
                json.dumps([asdict(deviation) for deviation in session.deviations]),
                session.user_clock_ms,
                session.bot_clock_ms,
                json.dumps(session.ui),
                session.pgn(),
                eco,
                opening,
                __version__,
                session.engine_name,
                "app",
                white,
                black,
                content_hash(
                    white,
                    black,
                    session.started_at.strftime("%Y.%m.%d"),
                    tuple(record.uci for record in session.moves),
                ),
                json.dumps(
                    {
                        "setup": asdict(session.bot_deviation_setup)
                        if session.bot_deviation_setup
                        else None,
                        "deviation": asdict(session.bot_deviation)
                        if session.bot_deviation
                        else None,
                    }
                ),
            ],
        )

    def save_imported(
        self, games: Sequence[ImportedGame], new_id: Callable[[], str]
    ) -> tuple[int, int]:
        """Saves the imported games not seen before.

        A duplicate of an imported game replaces its PGN when it carries more analysis, such as
        the same game downloaded from the site's analysis page after a plain export. A game played
        here is never replaced.

        Args:
            games (Sequence[ImportedGame]): The games read from PGN.
            new_id (Callable[[], str]): Makes a new game id.

        Returns:
            tuple[int, int]: (duplicates skipped, duplicates updated).
        """
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT content_hash, game_id, source, pgn FROM games WHERE content_hash IS NOT NULL"
        )
        known = {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}
        duplicates = updated = 0
        cursor.begin()
        try:
            for game in games:
                if game.content_hash in known:
                    game_id, source, pgn = known[game.content_hash]
                    if source == "imported" and game.notes > annotation_count_of(pgn):
                        cursor.execute(
                            "UPDATE games SET pgn = ? WHERE game_id = ?", [game.pgn, game_id]
                        )
                        known[game.content_hash] = (game_id, source, game.pgn)
                        updated += 1
                    else:
                        duplicates += 1
                    continue
                game_id = new_id()
                known[game.content_hash] = (game_id, "imported", game.pgn)
                moves = [
                    {"ply": ply, "san": san, "uci": uci}
                    for ply, (san, uci) in enumerate(zip(game.sans, game.ucis, strict=True), 1)
                ]
                cursor.execute(
                    "INSERT INTO games VALUES "
                    "(?, 'finished', ?, ?, '', ?, '', '', [], '', ?, '', false, 0, ?, '[]', "
                    "NULL, NULL, '{}', ?, ?, ?, ?, '', 'imported', ?, ?, ?, NULL)",
                    [
                        game_id,
                        game.played_at.replace(tzinfo=None),
                        datetime.now(UTC).replace(tzinfo=None),
                        game.time_control,
                        game.result,
                        json.dumps(moves),
                        game.pgn,
                        game.eco,
                        game.opening,
                        __version__,
                        game.white,
                        game.black,
                        game.content_hash,
                    ],
                )
            cursor.commit()
        except Exception:
            cursor.rollback()
            raise
        return duplicates, updated

    def finished_games(self) -> list[dict]:
        """The finished games for the Saved games list, newest first.

        Returns:
            list[dict]: One summary per game, with `plies`, `sans` and `chess960` added.
        """
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT game_id, started_at, user_color, time_control, level, result, termination, "
            "eco, opening, source, white, black, moves_json, pgn FROM games "
            "WHERE status = 'finished' "
            "ORDER BY started_at DESC, game_id DESC"
        )
        columns = [column[0] for column in cursor.description]
        games = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        for game in games:
            moves = json.loads(game.pop("moves_json"))
            game["plies"] = len(moves)
            game["sans"] = [move["san"] for move in moves]
            game["chess960"] = "chess960" in game.pop("pgn").lower()
            game["started_at"] = f"{game['started_at'].isoformat()}Z"
        return games

    def game_line(self, key: str) -> Variant | None:
        """A saved game as a line of the book.

        Args:
            key (str): `game:<game id>:<plies to follow>`.

        Returns:
            Variant | None: The line, or None if the game is unknown, has a `[FEN]` or no moves.
        """
        _, game_id, plies = key.split(":")
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT eco, opening, pgn, moves_json FROM games "
            "WHERE game_id = ? AND status = 'finished'",
            [game_id],
        )
        row = cursor.fetchone()
        if row is None or "[fen " in row[2].lower():
            return None
        eco, opening, _, moves_json = row
        moves = json.loads(moves_json)[: int(plies)]
        if not moves:
            return None
        board = chess.Board()
        rows = []
        for ply, move in enumerate(moves, 1):
            rows.append(BookMoveRow(board.epd(), ply, move["uci"], move["san"]))
            board.push_uci(move["uci"])
        final_epd = board.epd()
        book_moves, positions = index_moves(rows, final_epd)
        return Variant(
            variant_id=key,
            repertoire_id="saved-games",
            names={"en": opening or "Saved game"},
            eco=eco,
            opening=opening,
            source=f"game {game_id}",
            pgn=" ".join(move["san"] for move in moves),
            moves=book_moves,
            positions=positions,
            final_epd=final_epd,
        )

    def finished_game(self, game_id: str) -> dict | None:
        """One finished game, for its review.

        Args:
            game_id (str): The game's id.

        Returns:
            dict | None: Its PGN, players, result, opening, source, user color, level, moves
                and deviations, or None.
        """
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT pgn, white, black, result, eco, opening, source, user_color, level, "
            "moves_json, deviations_json, bot_deviation_json "
            "FROM games "
            "WHERE game_id = ? AND status = 'finished'",
            [game_id],
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip([column[0] for column in cursor.description], row, strict=True))

    def finished_pgns(self, game_ids: Sequence[str]) -> dict[str, str]:
        """The PGNs of finished games, oldest first, the natural order for a PGN file.

        Args:
            game_ids (Sequence[str]): The games wanted.

        Returns:
            dict[str, str]: Game id -> PGN, for those that exist and are finished.
        """
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT game_id, pgn FROM games "
            "WHERE status = 'finished' AND list_contains(?, game_id) "
            "ORDER BY started_at, game_id",
            [list(game_ids)],
        )
        return dict(cursor.fetchall())

    def delete_finished(self, game_ids: Sequence[str]) -> int:
        """Deletes finished games for good. An active game is never deleted: resigning ends it.

        Args:
            game_ids (Sequence[str]): The games to delete.

        Returns:
            int: How many rows were deleted.
        """
        cursor = self._connection.cursor()
        cursor.execute(
            "DELETE FROM games WHERE status = 'finished' AND list_contains(?, game_id)",
            [list(game_ids)],
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def active_row(self) -> dict | None:
        """The row of the unfinished game, if any.

        Returns:
            dict | None: The row by column name, or None.
        """
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT * FROM games WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip([column[0] for column in cursor.description], row, strict=True))


def restore_session(
    row: Mapping,
    book: Book,
    opening_names: Mapping[str, tuple[str, str]],
    rng: random.Random,
    store: GameStore,
) -> GameSession | None:
    """Rebuilds a session by replaying its saved moves.

    Args:
        row (Mapping): The game's row.
        book (Book): The book, for its lines.
        opening_names (Mapping[str, tuple[str, str]]): EPD -> (ECO, name).
        rng (random.Random): The random source.
        store (GameStore): The store, for lines made from saved games.

    Returns:
        GameSession | None: The session, or None if none of its lines exist anymore.
    """
    known = dict(book.variants)
    chess960_position = None
    for key in row["variant_ids"]:
        if key.startswith(CHESS960_PREFIX):
            chess960_position = int(key.removeprefix(CHESS960_PREFIX))
            known[key] = chess960_line(chess960_position)
        elif key.startswith(GAME_LINE_PREFIX):
            line = store.game_line(key)
            if line is not None:
                known[key] = line
    variants = [known[key] for key in row["variant_ids"] if key in known]
    if not variants:
        return None
    session = GameSession(
        game_id=row["game_id"],
        selection=Selection(variants),
        user_color=chess.WHITE if row["user_color"] == "white" else chess.BLACK,
        time_control_key=row["time_control"],
        time_control=TIME_CONTROLS.get(row["time_control"]),
        level=row["level"],
        pace=row["pace"],
        rng=rng,
        opening_names=opening_names,
        engine_name=row["engine_name"],
        chess960_position=chess960_position,
    )
    session.started_at = row["started_at"].replace(tzinfo=UTC)
    session.variant = known.get(row["current_variant_id"], variants[0])
    for raw in json.loads(row["moves_json"]):
        opening = raw.pop("opening")
        record = MoveRecord(**raw, opening=tuple(opening) if opening else None)
        session.board.push_uci(record.uci)
        session.moves.append(record)
    session.deviations = [
        Deviation(item["ply"], item["played_san"], tuple(item["expected_san"]))
        for item in json.loads(row["deviations_json"])
    ]
    session.in_theory = row["in_theory"]
    session.theory_until_ply = row["theory_until_ply"]
    session.user_clock_ms = row["user_clock_ms"]
    session.bot_clock_ms = row["bot_clock_ms"]
    session.ui = json.loads(row["ui_json"])
    bot_deviation = json.loads(row.get("bot_deviation_json") or "{}")
    if bot_deviation.get("setup"):
        session.bot_deviation_setup = BotDeviationSetup(**bot_deviation["setup"])
    if bot_deviation.get("deviation"):
        item = bot_deviation["deviation"]
        session.bot_deviation = Deviation(
            item["ply"], item["played_san"], tuple(item["expected_san"])
        )
    if row["result"]:
        session.outcome = GameResult(row["result"], row["termination"])
    return session
