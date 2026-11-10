"""Games are saved on every move and continue after the app restarts."""

import asyncio
import dataclasses
import io
import random
import re
from datetime import UTC, datetime

import chess.pgn
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.connection import open_database
from app.engine.process import EngineUnavailableError
from app.game.pace import TIME_CONTROLS, clock_after_move
from app.game.service import new_game_id
from app.main import create_app
from tests.conftest import NO_BOOK_EVALS, FakeEngine

ALAPIN_PGN = "1. e4 c5 2. c3"


class BrokenEngine(FakeEngine):
    """An engine whose every search fails."""

    async def play(self, board, level, max_time_s=None):
        """Fails.

        Args:
            board (chess.Board): The position.
            level (Level): The level.
            max_time_s (float | None): The time limit.

        Raises:
            EngineUnavailableError: Always.
        """
        raise EngineUnavailableError("down")


def app_on(path, engine=None):
    """An API client on a database file, as if the app restarted on it.

    Args:
        path (Path): The database.
        engine (FakeEngine | None): The engine; a new fake when None.

    Returns:
        TestClient: The client; start it with `with`.
    """
    settings = dataclasses.replace(Settings(), database_path=path, book_evals_file=NO_BOOK_EVALS)
    return TestClient(
        create_app(settings, engine=engine or FakeEngine(), rng=random.Random(3)),
        base_url="http://127.0.0.1",
    )


def alapin_id(client):
    """The id of the Alapin line, 1. e4 c5 2. c3.

    Args:
        client (TestClient): The API client.

    Returns:
        str: The line id.
    """
    repertoires = client.get("/api/repertoires").json()["repertoires"]
    return next(
        v["variant_id"] for r in repertoires for v in r["variants"] if v["pgn"] == ALAPIN_PGN
    )


def start(client, color="white", time_control="3i2", ui=None):
    """Starts an Alapin game with the Instant pace.

    Args:
        client (TestClient): The API client.
        color (str): The user's color.
        time_control (str): The time control's key.
        ui (dict | None): UI flags to save.

    Returns:
        dict: The API's response body.
    """
    return client.post(
        "/api/games",
        json={
            "color": color,
            "variant_ids": [alapin_id(client)],
            "level": "club",
            "pace": "instant",
            "time_control": time_control,
            "ui": ui or {},
        },
    ).json()


def row(path):
    """The saved games, newest first, read from the file.

    Args:
        path (Path): The database.

    Returns:
        list[tuple]: (status, result, termination, pgn) per game.
    """
    database = open_database(path)
    found = database.execute(
        "SELECT status, result, termination, pgn FROM games ORDER BY started_at DESC"
    ).fetchall()
    database.close()
    return found


def test_game_id_is_a_timestamp_and_a_random_part():
    """Game id is a timestamp and a random part."""
    now = datetime(2026, 11, 7, 13, 11, 59, 12345, tzinfo=UTC)
    first, second = new_game_id(now), new_game_id(now)
    assert re.fullmatch(r"20261107131159012345-[a-z0-9]{12}-[a-z0-9]{12}", first)
    assert first != second
    assert new_game_id(now) < new_game_id(now.replace(year=2027))


def test_game_id_works_through_the_api(client):
    """Game id works through the API.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    game_id = start(client)["state"]["game_id"]
    assert re.fullmatch(r"\d{20}-[a-z0-9]{12}-[a-z0-9]{12}", game_id)
    assert client.get(f"/api/games/{game_id}").status_code == 200


def finish(client, color="white"):
    """Starts a game and resigns it.

    Args:
        client (TestClient): The API client.
        color (str): The user's color.

    Returns:
        str: The game's id.
    """
    game_id = start(client, color=color)["state"]["game_id"]
    client.post(f"/api/games/{game_id}/resign")
    return game_id


def test_saved_list_has_only_finished_games_newest_first(client):
    """Saved list has only finished games newest first.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert client.get("/api/games").json() == {"games": []}
    first = finish(client)
    second = finish(client, color="black")
    start(client)  # still active
    games = client.get("/api/games").json()["games"]
    assert [game["game_id"] for game in games] == [second, first]
    newest = games[0]
    assert newest["user_color"] == "black"
    assert newest["result"] == "loss"
    assert newest["time_control"] == "3i2"
    assert newest["plies"] == 1
    assert newest["started_at"].endswith("Z")
    assert newest["opening"] == "King's Pawn Game"
    assert "pgn" not in newest


def test_export_joins_the_selected_games_oldest_first(client):
    """Export joins the selected games oldest first.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    first = finish(client, color="black")
    second = finish(client, color="white")
    third = finish(client, color="black")
    response = client.post("/api/games/export", json={"game_ids": [third, first]})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-chess-pgn")
    assert "attachment" in response.headers["content-disposition"]
    games = []
    handle = io.StringIO(response.text)
    while (game := chess.pgn.read_game(handle)) is not None:
        games.append(game)
    assert len(games) == 2
    assert all(game.headers["Termination"] == "Normal" for game in games)
    assert second not in response.text


def test_export_refuses_unknown_empty_and_active_games(client):
    """Export refuses unknown empty and active games.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    active = start(client)["state"]["game_id"]
    assert client.post("/api/games/export", json={"game_ids": []}).status_code == 422
    assert client.post("/api/games/export", json={"game_ids": ["nope"]}).status_code == 422
    assert client.post("/api/games/export", json={"game_ids": [active]}).status_code == 422


GOOD = """[White "Ana"]
[Black "Bia"]
[Date "2026.03.04"]
[Result "1-0"]

1. e4 c6 2. d4 { a comment } d5 (2... g6 3. Nf3) 3. e5 1-0
"""
ILLEGAL = """[White "Illegal"]
[Black "X"]

1. e4 e4 *
"""
CUSTOM = """[White "Custom"]
[Black "X"]
[SetUp "1"]
[FEN "8/P6k/8/8/8/8/8/K7 w - - 0 1"]

1. a8=Q *
"""
FISCHER = """[White "Fischer"]
[Black "Random"]
[Variant "Chess960"]
[SetUp "1"]
[FEN "nrkbbrqn/pppppppp/8/8/8/8/PPPPPPPP/NRKBBRQN w KQkq - 0 1"]
[Result "*"]

1. e4 e5 *
"""


def do_import(client, text):
    """Imports PGN text.

    Args:
        client (TestClient): The API client.
        text (str): The PGN.

    Returns:
        dict: The import report.
    """
    return client.post("/api/games/import", json={"pgn": text}).json()


def test_import_a_game_keeps_comments_and_side_lines(client):
    """Import a game keeps comments and side lines.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert do_import(client, GOOD) == {"imported": 1, "duplicates": 0, "updated": 0, "errors": []}
    game = client.get("/api/games").json()["games"][0]
    assert game["source"] == "imported"
    assert (game["white"], game["black"]) == ("Ana", "Bia")
    assert game["result"] == "1-0"
    assert game["plies"] == 5
    assert game["started_at"].startswith("2026-03-04")
    assert game["opening"] == "Caro-Kann Defense: Advance Variation"
    text = client.post("/api/games/export", json={"game_ids": [game["game_id"]]}).text
    assert "a comment" in text
    assert "( 2... g6 3. Nf3 )" in text


def test_name_and_eco_come_from_the_same_place(client):
    """Name and ECO come from the same place.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    moves = "1. e4 e5 2. Nc3 *"
    do_import(client, f'[White "A"]\n[Black "B"]\n[ECO "B50"]\n\n{moves}\n')
    do_import(client, f'[White "C"]\n[Black "D"]\n[ECO "A00"]\n[Opening "Mine"]\n\n{moves}\n')
    games = {game["white"]: game for game in client.get("/api/games").json()["games"]}
    assert (games["A"]["eco"], games["A"]["opening"]) == ("C25", "Vienna Game")
    assert (games["C"]["eco"], games["C"]["opening"]) == ("A00", "Mine")


def test_one_bad_game_does_not_stop_the_others(client):
    """One bad game does not stop the others.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    report = do_import(client, ILLEGAL + "\n" + GOOD + "\n" + CUSTOM)
    assert report["imported"] == 1
    assert [(e["index"], e["label"], e["code"]) for e in report["errors"]] == [
        (1, "Illegal - X", "invalid_moves"),
        (3, "Custom - X", "custom_position"),
    ]


def test_duplicates_are_skipped_in_one_text_and_across_imports(client):
    """Duplicates are skipped in one text and across imports.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert do_import(client, GOOD + "\n" + GOOD)["duplicates"] == 1
    assert do_import(client, GOOD) == {"imported": 0, "duplicates": 1, "updated": 0, "errors": []}
    assert len(client.get("/api/games").json()["games"]) == 1


def test_a_game_exported_from_the_app_is_a_duplicate(client, engine):
    """A game exported from the app is a duplicate.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        engine (FakeEngine): The fake engine the client uses.
    """
    game_id = start(client)["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4"})
    client.post(f"/api/games/{game_id}/resign")
    exported = client.post("/api/games/export", json={"game_ids": [game_id]}).text
    assert do_import(client, exported) == {
        "imported": 0,
        "duplicates": 1,
        "updated": 0,
        "errors": [],
    }
    # A game played here keeps its own PGN, even when the copy brings analysis.
    annotated = exported.replace("1. e4 ", "1. e4 $2 { a note } ", 1)
    assert do_import(client, annotated)["updated"] == 0
    assert "a note" not in client.post("/api/games/export", json={"game_ids": [game_id]}).text


def test_chess960_is_accepted_and_exported_with_its_position(client):
    """Chess960 is accepted and exported with its position.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert do_import(client, FISCHER)["imported"] == 1
    game = client.get("/api/games").json()["games"][0]
    assert game["opening"] is None
    text = client.post("/api/games/export", json={"game_ids": [game["game_id"]]}).text
    assert '[Variant "Chess960"]' in text
    assert "nrkbbrqn" in text


def test_loose_text_and_empty_input_import_nothing(client):
    """Loose text and empty input import nothing.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert do_import(client, "")["imported"] == 0
    assert do_import(client, "8/P6k/8/8/8/8/8/K7 w - - 0 1")["imported"] == 0
    assert client.get("/api/games").json() == {"games": []}


def test_other_variants_are_refused(client):
    """Other variants are refused.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    atomic = '[Variant "Atomic"]\n[White "A"]\n[Black "B"]\n\n1. e4 e5 *\n'
    assert do_import(client, atomic)["errors"][0]["code"] == "unsupported_variant"


def test_imported_games_never_become_active(client):
    """Imported games never become active.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    do_import(client, GOOD)
    assert client.get("/api/games/active").json() == {"game": None}


def new_from(client, game_id, color="white", **options):
    """Starts a game from a saved one.

    Args:
        client (TestClient): The API client.
        game_id (str): The saved game.
        color (str): The user's color.
        **options (object): Other fields of `from_game`, such as `upto_ply` or `mode`.

    Returns:
        Response: The API's response.
    """
    return client.post(
        "/api/games",
        json={
            "color": color,
            "from_game": {"game_id": game_id, **options},
            "level": "club",
            "pace": "instant",
            "time_control": "none",
        },
    )


def imported_id(client, text=GOOD):
    """Imports a game and returns its id.

    Args:
        client (TestClient): The API client.
        text (str): The PGN.

    Returns:
        str: The newest saved game's id.
    """
    do_import(client, text)
    return client.get("/api/games").json()["games"][0]["game_id"]


def test_saved_list_gives_the_moves_for_choosing_a_point(client):
    """Saved list gives the moves for choosing a point.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    imported_id(client)
    game = client.get("/api/games").json()["games"][0]
    assert game["sans"] == ["e4", "c6", "d4", "d5", "e5"]
    assert game["chess960"] is False


def test_train_a_saved_games_line_as_black(client, engine):
    """Train a saved game's line as black.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        engine (FakeEngine): The fake engine the client uses.
    """
    game_id = imported_id(client)
    body = new_from(client, game_id, color="black").json()
    assert body["bot_move"]["san"] == "e4"
    assert body["bot_move"]["source"] == "book"
    active = body["state"]["game_id"]
    body = client.post(f"/api/games/{active}/moves", json={"uci": "c7c6"}).json()
    assert body["deviation"] is None
    assert body["bot_move"]["san"] == "d4"
    body = client.post(f"/api/games/{active}/moves", json={"uci": "e7e6"}).json()
    assert body["deviation"]["expected_san"] == ["d5"]
    assert body["bot_move"]["source"] == "engine"


def test_line_stops_at_the_chosen_move(client, engine):
    """Line stops at the chosen move.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        engine (FakeEngine): The fake engine the client uses.
    """
    game_id = imported_id(client)
    body = new_from(client, game_id, upto_ply=2).json()
    active = body["state"]["game_id"]
    body = client.post(f"/api/games/{active}/moves", json={"uci": "e2e4"}).json()
    assert body["bot_move"]["san"] == "c6"
    body = client.post(f"/api/games/{active}/moves", json={"uci": "d2d4"}).json()
    assert body["deviation"] is None
    assert body["bot_move"]["source"] == "engine"


def test_from_position_starts_at_the_chosen_move(client, engine):
    """From position starts at the chosen move.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        engine (FakeEngine): The fake engine the client uses.
    """
    game_id = imported_id(client)
    response = new_from(client, game_id, upto_ply=3, mode="position")
    assert response.status_code == 201
    game = client.get("/api/games/active").json()["game"]
    assert [move["san"] for move in game["moves"]][:3] == ["e4", "c6", "d4"]
    assert len(game["moves"]) == 4  # as White, the bot had to answer 2.d4
    assert game["moves"][3]["by"] == "bot"
    assert engine.calls == 1


def test_from_position_with_the_user_to_move_waits(client, engine):
    """From position with the user to move waits.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        engine (FakeEngine): The fake engine the client uses.
    """
    game_id = imported_id(client)
    new_from(client, game_id, upto_ply=4, mode="position")
    game = client.get("/api/games/active").json()["game"]
    assert len(game["moves"]) == 4
    assert engine.calls == 0


def test_game_from_a_saved_game_survives_a_restart(database_path):
    """Game from a saved game survives a restart.

    Args:
        database_path (Path): This test's copy of the database.
    """
    with app_on(database_path) as client:
        game_id = imported_id(client)
        active = new_from(client, game_id, upto_ply=4).json()["state"]["game_id"]
        client.post(f"/api/games/{active}/moves", json={"uci": "e2e4"})
    with app_on(database_path) as client:
        game = client.get("/api/games/active").json()["game"]
        assert game["state"]["game_id"] == active
        assert game["setup"]["variant_ids"] == [f"game:{game_id}:4"]
        body = client.post(f"/api/games/{active}/moves", json={"uci": "d2d4"}).json()
        assert body["bot_move"]["san"] == "d5"


@pytest.mark.parametrize(
    "options",
    [{"upto_ply": 99}, {"game_id": "nope"}],
)
def test_bad_start_points_are_refused(client, options):
    """Bad start points are refused.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        options (dict): Fields of `from_game` that make the start point invalid.
    """
    game_id = imported_id(client)
    payload = {"game_id": game_id, **options}
    assert new_from(client, **{"game_id": payload.pop("game_id"), **payload}).status_code == 422


def test_chess960_games_cannot_be_played_from_yet(client):
    """Chess960 games cannot be played from yet.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    do_import(client, FISCHER)
    game = client.get("/api/games").json()["games"][0]
    assert game["chess960"] is True
    assert new_from(client, game["game_id"]).status_code == 422


def test_a_standard_game_that_mentions_chess960_is_not_chess960(client):
    """Only the Variant tag makes a game Chess960, not the word in an event or a comment.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    text = GOOD.replace('[White "Ana"]', '[Event "Chess960 club night"]\n[White "Ana"]')
    game_id = imported_id(client, text.replace("1. e4", "1. e4 { as in chess960 }"))
    assert client.get("/api/games").json()["games"][0]["chess960"] is False
    assert client.get(f"/api/games/{game_id}/review").json()["chess960"] is False
    assert new_from(client, game_id).status_code == 201


def test_active_game_cannot_be_played_from(client):
    """Active game cannot be played from.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    active = start(client)["state"]["game_id"]
    assert new_from(client, active).status_code == 422


def test_starting_with_nothing_is_refused(client):
    """Starting with nothing is refused.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    body = {"color": "white", "level": "club", "pace": "instant", "time_control": "none"}
    assert client.post("/api/games", json=body).status_code == 422


def test_review_of_a_saved_game_has_every_position(client):
    """Review of a saved game has every position.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    game_id = imported_id(client)
    body = client.get(f"/api/games/{game_id}/review").json()
    assert body["start_fen"].startswith("rnbqkbnr/pppppppp")
    assert [move["san"] for move in body["moves"]] == ["e4", "c6", "d4", "d5", "e5"]
    assert body["moves"][0]["uci"] == "e2e4"
    assert body["moves"][0]["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3")
    assert (body["white"], body["black"], body["result"]) == ("Ana", "Bia", "1-0")
    assert body["chess960"] is False
    assert body["source"] == "imported"


def test_review_of_a_played_game_says_who_was_the_user(client):
    """A played game tells the review the user's color and the bot's level.

    The browser then names the players in the chosen language instead of the PGN's English.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    game_id = finish(client, color="black")
    body = client.get(f"/api/games/{game_id}/review").json()
    assert (body["source"], body["user_color"]) == ("app", "black")
    assert body["level"]
    assert body["black"] == "You"


def test_review_of_a_chess960_game_starts_from_its_position(client):
    """Review of a Chess960 game starts from its position.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    do_import(client, FISCHER)
    game_id = client.get("/api/games").json()["games"][0]["game_id"]
    body = client.get(f"/api/games/{game_id}/review").json()
    assert body["start_fen"].startswith("nrkbbrqn")
    assert body["chess960"] is True
    assert len(body["moves"]) == 2


def test_review_of_a_book_line(client):
    """Review of a book line.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    repertoires = client.get("/api/repertoires").json()["repertoires"]
    line = next(v for r in repertoires for v in r["variants"] if v["pgn"] == "1. e4 c5 2. c3")
    body = client.get(f"/api/lines/{line['variant_id']}/review").json()
    assert [move["san"] for move in body["moves"]] == ["e4", "c5", "c3"]
    assert body["white"] is None
    assert body["opening"] == "Sicilian Defense: Alapin Variation"


def test_review_of_unknown_or_active_games_is_refused(client):
    """Review of unknown or active games is refused.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    active = start(client)["state"]["game_id"]
    assert client.get(f"/api/games/{active}/review").status_code == 404
    assert client.get("/api/games/nope/review").status_code == 404
    assert client.get("/api/lines/nope/review").status_code == 404


def test_no_active_game_at_first(client):
    """No active game at first.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert client.get("/api/games/active").json() == {"game": None}


def test_active_game_comes_back_while_the_server_runs(client):
    """Active game comes back while the server runs.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    # "scoresheet" is a flag of a removed mode: old games keep it, and the page ignores it.
    ui = {"warning": False, "scoresheet": True}
    game_id = start(client, ui=ui)["state"]["game_id"]
    client.post(
        f"/api/games/{game_id}/moves",
        json={"uci": "e2e4", "user_clock_ms": 170_000, "bot_clock_ms": 180_000},
    )
    game = client.get("/api/games/active").json()["game"]
    assert game["state"]["game_id"] == game_id
    assert [move["san"] for move in game["moves"]] == ["e4", "c5"]
    assert game["setup"]["ui"] == ui
    assert game["setup"]["time_control"] == "3i2"
    assert game["clocks"] == {"user_ms": 170_000, "bot_ms": 182_000}


def test_game_continues_after_a_restart(database_path):
    """Game continues after a restart.

    Args:
        database_path (Path): This test's copy of the database.
    """
    with app_on(database_path) as client:
        game_id = start(client)["state"]["game_id"]
        client.post(f"/api/games/{game_id}/moves", json={"uci": "d2d4"})  # a deviation
    with app_on(database_path) as client:
        game = client.get("/api/games/active").json()["game"]
        assert game["state"]["game_id"] == game_id
        assert [move["deviation"] for move in game["moves"]] == [True, False]
        assert game["state"]["in_theory"] is False
        # It really continues: the next move and the final report work.
        side = client.get(f"/api/games/{game_id}").json()
        assert side["deviations"][0]["played_san"] == "d4"
        uci = "g1f3"
        assert client.post(f"/api/games/{game_id}/moves", json={"uci": uci}).status_code == 200
        summary = client.post(f"/api/games/{game_id}/resign").json()
        assert summary["result"] == "loss"
        assert client.get("/api/games/active").json() == {"game": None}
    assert row(database_path)[0][:2] == ("finished", "loss")


def test_a_move_is_saved_before_the_bot_answers(database_path):
    """A move is saved before the bot answers.

    Args:
        database_path (Path): This test's copy of the database.
    """
    with app_on(database_path, BrokenEngine()) as client:
        game_id = start(client)["state"]["game_id"]
        for uci in ("e2e4", "c2c3"):  # the book ends here, so the engine has to answer
            response = client.post(f"/api/games/{game_id}/moves", json={"uci": uci})
        assert response.status_code == 503
    with app_on(database_path) as client:
        game = client.get("/api/games/active").json()["game"]
        assert [move["san"] for move in game["moves"]][:3] == ["e4", "c5", "c3"]
        assert len(game["moves"]) == 4  # the bot's missing reply is played on resume
        assert game["moves"][3]["by"] == "bot"


def test_chess960_game_continues_after_a_restart(database_path):
    """Chess960 game continues after a restart.

    Args:
        database_path (Path): This test's copy of the database.
    """
    fen = "bbqnrkrn/pppppppp/8/8/8/8/PPPPPPPP/BBQNRKRN w KQkq - 0 1"
    setup = {"level": "club", "pace": "instant", "time_control": "none"}
    with app_on(database_path) as client:
        body = {"color": "white", "chess960_position": 288, **setup}
        game_id = client.post("/api/games", json=body).json()["state"]["game_id"]
        played = client.post(f"/api/games/{game_id}/moves", json={"uci": "f1g1"})
        assert played.json()["user_move"]["san"] == "O-O"
    with app_on(database_path) as client:
        game = client.get("/api/games/active").json()["game"]
        assert game["setup"]["chess960"] == {"position": 288, "fen": fen}
        assert game["state"]["game_id"] == game_id
        assert game["moves"][0]["san"] == "O-O"
        assert game["state"]["left_theory_at_move"] is None
        assert client.post(f"/api/games/{game_id}/moves", json={"uci": "a2a3"}).status_code == 200
        pgn = client.post(f"/api/games/{game_id}/resign").json()["pgn"]
        assert f'[FEN "{fen}"]' in pgn


def test_resume_is_idempotent(client):
    """Resume is idempotent.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    game_id = start(client, color="black")["state"]["game_id"]
    assert game_id
    first = client.get("/api/games/active").json()["game"]["moves"]
    assert client.get("/api/games/active").json()["game"]["moves"] == first


def test_finished_game_is_kept_with_its_pgn(database_path):
    """Finished game is kept with its PGN.

    Args:
        database_path (Path): This test's copy of the database.
    """
    with app_on(database_path) as client:
        game_id = start(client)["state"]["game_id"]
        client.post(
            f"/api/games/{game_id}/moves",
            json={"uci": "e2e4", "user_clock_ms": 170_000, "bot_clock_ms": 180_000},
        )
        client.post(f"/api/games/{game_id}/resign")
    status, result, termination, pgn = row(database_path)[0]
    assert (status, result, termination) == ("finished", "loss", "resignation")
    assert '[Termination "Normal"]' in pgn
    assert '[Black "Fake Engine 1 (club)"]' in pgn
    assert "[VariantId " in pgn
    assert "[%clk 0:02:50]" in pgn


def test_starting_over_an_active_game_gives_it_up(client):
    """Starting over an active game gives it up.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    first = start(client)["state"]["game_id"]
    second = start(client)["state"]["game_id"]
    assert client.get("/api/games/active").json()["game"]["state"]["game_id"] == second
    assert first != second


def test_timeout_pgn_says_time_forfeit(client):
    """Timeout PGN says time forfeit.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    game_id = start(client)["state"]["game_id"]
    body = client.post(
        f"/api/games/{game_id}/timeout", json={"side": "user", "shown_plies": 0}
    ).json()
    assert '[Termination "Time forfeit"]' in body["pgn"]


@pytest.mark.parametrize(
    ("key", "remaining", "used", "moves_made", "expected"),
    [
        ("3i2", 100_000, 3_000, 1, 99_000),
        ("25d10", 100_000, 3_000, 1, 100_000),
        ("25d10", 100_000, 15_000, 1, 95_000),
        ("25u5", 100_000, 3_000, 1, 100_000),
        ("25u5", 100_000, 15_000, 1, 90_000),
        ("120+30", 100_000, 0, 40, 1_900_000),
        ("120+60+30", 100_000, 0, 60, 1_900_000),
        ("5", 1_000, 5_000, 1, 0),
    ],
)
def test_clock_after_move_matches_the_browser_rules(key, remaining, used, moves_made, expected):
    """Clock after move matches the browser rules.

    Args:
        key (str): A time control key.
        remaining (int): The clock before the move, in milliseconds.
        used (int): How long the move took, in milliseconds.
        moves_made (int): The player's moves, this one included.
        expected (int): The clock after the move, in milliseconds.
    """
    assert clock_after_move(TIME_CONTROLS[key], remaining, used, moves_made) == expected


class SlowEngine(FakeEngine):
    """An engine that waits before each move.

    Attributes:
        seconds (float): How long each search takes.
    """

    def __init__(self, seconds: float) -> None:
        """Creates the engine.

        Args:
            seconds (float): How long each search takes.
        """
        super().__init__()
        self.seconds = seconds

    async def play(self, board, level, max_time_s=None):
        """Waits, then plays like the fake engine.

        Args:
            board (chess.Board): The position.
            level (Level): The level.
            max_time_s (float | None): The time limit.

        Returns:
            chess.Move: The move.
        """
        await asyncio.sleep(self.seconds)
        return await super().play(board, level, max_time_s)


def bullet_as_black(client, pace: str) -> dict:
    """Starts a 30 s Chess960 game as Black, so the engine plays the first move.

    Args:
        client (TestClient): The API client.
        pace (str): The bot's pace.

    Returns:
        dict: The API's response body.
    """
    body = {
        "color": "black",
        "chess960_position": 288,
        "level": "club",
        "pace": pace,
        "time_control": "30s",
    }
    return client.post("/api/games", json=body).json()


def test_the_search_comes_off_the_bots_clock(database_path):
    """The search comes off the bot's clock.

    Args:
        database_path (Path): This test's copy of the database.
    """
    with app_on(database_path, SlowEngine(0.2)) as client:
        assert bullet_as_black(client, "instant")["bot_move"]["delay_ms"] == 0
        game = client.get("/api/games/active").json()["game"]
        assert 25_000 < game["clocks"]["bot_ms"] <= 29_800


def test_a_search_inside_the_human_delay_costs_only_the_delay(database_path):
    """A search inside the human delay costs only the delay.

    Args:
        database_path (Path): This test's copy of the database.
    """
    with app_on(database_path, SlowEngine(0.02)) as client:
        delay_ms = bullet_as_black(client, "human")["bot_move"]["delay_ms"]
        game = client.get("/api/games/active").json()["game"]
        assert game["clocks"]["bot_ms"] == 30_000 - delay_ms


PLAIN = """[White "Ana"]
[Black "Bia"]
[Date "2026.05.06"]
[Result "1-0"]

1. e4 {[%clk 0:02:59]} e6 {[%clk 0:02:58]} 2. d4 d5 1-0
"""
ANALYSED = """[White "Ana"]
[Black "Bia"]
[Date "2026.05.06"]
[Result "1-0"]

1. e4 {[%clk 0:02:59]} e6 $6 {[%clk 0:02:58] a passive move} 2. d4 d5 (2... c5) 1-0
"""


def saved_pgn(client):
    """The exported PGN of the only saved game.

    Args:
        client (TestClient): The API client.

    Returns:
        str: The PGN.
    """
    [game] = client.get("/api/games").json()["games"]
    return client.post("/api/games/export", json={"game_ids": [game["game_id"]]}).text


def test_a_duplicate_with_more_analysis_replaces_the_saved_pgn(client):
    """A duplicate with more analysis replaces the saved PGN.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert do_import(client, PLAIN)["imported"] == 1
    report = do_import(client, ANALYSED)
    assert (report["imported"], report["duplicates"], report["updated"]) == (0, 0, 1)
    assert "a passive move" in saved_pgn(client) and "( 2... c5 )" in saved_pgn(client)
    assert len(client.get("/api/games").json()["games"]) == 1


def test_a_duplicate_with_less_analysis_changes_nothing(client):
    """A duplicate with less analysis changes nothing.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    do_import(client, ANALYSED)
    for text in (PLAIN, ANALYSED):
        report = do_import(client, text)
        assert (report["duplicates"], report["updated"]) == (1, 0)
    assert "a passive move" in saved_pgn(client)


def test_the_richer_copy_wins_inside_one_import(client):
    """The richer copy wins inside one import.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    report = do_import(client, PLAIN + "\n" + ANALYSED)
    assert (report["imported"], report["updated"]) == (1, 1)
    assert "a passive move" in saved_pgn(client)


def test_deleting_saved_games_removes_them_for_good(client):
    """Deleting saved games removes them for good.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    do_import(client, GOOD + "\n" + PLAIN)
    games = client.get("/api/games").json()["games"]
    first, second = (g["game_id"] for g in games)
    assert client.post("/api/games/delete", json={"game_ids": [first]}).json() == {"deleted": 1}
    assert [g["game_id"] for g in client.get("/api/games").json()["games"]] == [second]
    assert client.get(f"/api/games/{first}/review").status_code == 404
    # Deleted means gone: the same game can be imported again.
    assert do_import(client, GOOD + "\n" + PLAIN)["imported"] == 1


def test_an_active_or_unknown_game_is_never_deleted(client):
    """An active or unknown game is never deleted.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    do_import(client, GOOD)
    [saved] = client.get("/api/games").json()["games"]
    active = start(client)["state"]["game_id"]
    for ids in ([active], [saved["game_id"], active], [saved["game_id"], "nope"], []):
        assert client.post("/api/games/delete", json={"game_ids": ids}).status_code == 422
    assert len(client.get("/api/games").json()["games"]) == 1
    assert client.get("/api/games/active").status_code == 200
