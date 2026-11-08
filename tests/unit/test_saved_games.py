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
    async def play(self, board, level, max_time_s=None):
        raise EngineUnavailableError("down")


def app_on(path, engine=None):
    settings = dataclasses.replace(Settings(), database_path=path, book_evals_file=NO_BOOK_EVALS)
    return TestClient(create_app(settings, engine=engine or FakeEngine(), rng=random.Random(3)))


def alapin_id(client):
    repertoires = client.get("/api/repertoires").json()["repertoires"]
    return next(
        v["variant_id"] for r in repertoires for v in r["variants"] if v["pgn"] == ALAPIN_PGN
    )


def start(client, color="white", time_control="3i2", ui=None):
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
    database = open_database(path)
    found = database.execute(
        "SELECT status, result, termination, pgn FROM games ORDER BY started_at DESC"
    ).fetchall()
    database.close()
    return found


def test_game_id_is_a_timestamp_and_a_random_part():
    now = datetime(2026, 11, 7, 13, 11, 59, 12345, tzinfo=UTC)
    first, second = new_game_id(now), new_game_id(now)
    assert re.fullmatch(r"20261107131159012345-[a-z0-9]{12}-[a-z0-9]{12}", first)
    assert first != second
    assert new_game_id(now) < new_game_id(now.replace(year=2027))


def test_game_id_works_through_the_api(client):
    game_id = start(client)["state"]["game_id"]
    assert re.fullmatch(r"\d{20}-[a-z0-9]{12}-[a-z0-9]{12}", game_id)
    assert client.get(f"/api/games/{game_id}").status_code == 200


def finish(client, color="white"):
    game_id = start(client, color=color)["state"]["game_id"]
    client.post(f"/api/games/{game_id}/resign")
    return game_id


def test_saved_list_has_only_finished_games_newest_first(client):
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
    return client.post("/api/games/import", json={"pgn": text}).json()


def test_import_a_game_keeps_comments_and_drops_side_lines(client):
    assert do_import(client, GOOD) == {"imported": 1, "duplicates": 0, "errors": []}
    game = client.get("/api/games").json()["games"][0]
    assert game["source"] == "imported"
    assert (game["white"], game["black"]) == ("Ana", "Bia")
    assert game["result"] == "1-0"
    assert game["plies"] == 5
    assert game["started_at"].startswith("2026-03-04")
    assert game["opening"] == "Caro-Kann Defense: Advance Variation"
    text = client.post("/api/games/export", json={"game_ids": [game["game_id"]]}).text
    assert "a comment" in text
    assert "g6" not in text


def test_name_and_eco_come_from_the_same_place(client):
    moves = "1. e4 e5 2. Nc3 *"
    do_import(client, f'[White "A"]\n[Black "B"]\n[ECO "B50"]\n\n{moves}\n')
    do_import(client, f'[White "C"]\n[Black "D"]\n[ECO "A00"]\n[Opening "Mine"]\n\n{moves}\n')
    games = {game["white"]: game for game in client.get("/api/games").json()["games"]}
    assert (games["A"]["eco"], games["A"]["opening"]) == ("C25", "Vienna Game")
    assert (games["C"]["eco"], games["C"]["opening"]) == ("A00", "Mine")


def test_one_bad_game_does_not_stop_the_others(client):
    report = do_import(client, ILLEGAL + "\n" + GOOD + "\n" + CUSTOM)
    assert report["imported"] == 1
    assert [(e["index"], e["label"], e["code"]) for e in report["errors"]] == [
        (1, "Illegal - X", "invalid_moves"),
        (3, "Custom - X", "custom_position"),
    ]


def test_duplicates_are_skipped_in_one_text_and_across_imports(client):
    assert do_import(client, GOOD + "\n" + GOOD)["duplicates"] == 1
    assert do_import(client, GOOD) == {"imported": 0, "duplicates": 1, "errors": []}
    assert len(client.get("/api/games").json()["games"]) == 1


def test_a_game_exported_from_the_app_is_a_duplicate(client, engine):
    game_id = start(client)["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4"})
    client.post(f"/api/games/{game_id}/resign")
    exported = client.post("/api/games/export", json={"game_ids": [game_id]}).text
    assert do_import(client, exported) == {"imported": 0, "duplicates": 1, "errors": []}


def test_chess960_is_accepted_and_exported_with_its_position(client):
    assert do_import(client, FISCHER)["imported"] == 1
    game = client.get("/api/games").json()["games"][0]
    assert game["opening"] is None
    text = client.post("/api/games/export", json={"game_ids": [game["game_id"]]}).text
    assert '[Variant "Chess960"]' in text
    assert "nrkbbrqn" in text


def test_loose_text_and_empty_input_import_nothing(client):
    assert do_import(client, "")["imported"] == 0
    assert do_import(client, "8/P6k/8/8/8/8/8/K7 w - - 0 1")["imported"] == 0
    assert client.get("/api/games").json() == {"games": []}


def test_other_variants_are_refused(client):
    atomic = '[Variant "Atomic"]\n[White "A"]\n[Black "B"]\n\n1. e4 e5 *\n'
    assert do_import(client, atomic)["errors"][0]["code"] == "unsupported_variant"


def test_imported_games_never_become_active(client):
    do_import(client, GOOD)
    assert client.get("/api/games/active").json() == {"game": None}


def new_from(client, game_id, color="white", **options):
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
    do_import(client, text)
    return client.get("/api/games").json()["games"][0]["game_id"]


def test_saved_list_gives_the_moves_for_choosing_a_point(client):
    imported_id(client)
    game = client.get("/api/games").json()["games"][0]
    assert game["sans"] == ["e4", "c6", "d4", "d5", "e5"]
    assert game["chess960"] is False


def test_train_a_saved_games_line_as_black(client, engine):
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
    game_id = imported_id(client)
    body = new_from(client, game_id, upto_ply=2).json()
    active = body["state"]["game_id"]
    body = client.post(f"/api/games/{active}/moves", json={"uci": "e2e4"}).json()
    assert body["bot_move"]["san"] == "c6"
    body = client.post(f"/api/games/{active}/moves", json={"uci": "d2d4"}).json()
    assert body["deviation"] is None
    assert body["bot_move"]["source"] == "engine"


def test_from_position_starts_at_the_chosen_move(client, engine):
    game_id = imported_id(client)
    response = new_from(client, game_id, upto_ply=3, mode="position")
    assert response.status_code == 201
    game = client.get("/api/games/active").json()["game"]
    assert [move["san"] for move in game["moves"]][:3] == ["e4", "c6", "d4"]
    assert len(game["moves"]) == 4  # as White, the bot had to answer 2.d4
    assert game["moves"][3]["by"] == "bot"
    assert engine.calls == 1


def test_from_position_with_the_user_to_move_waits(client, engine):
    game_id = imported_id(client)
    new_from(client, game_id, upto_ply=4, mode="position")
    game = client.get("/api/games/active").json()["game"]
    assert len(game["moves"]) == 4
    assert engine.calls == 0


def test_game_from_a_saved_game_survives_a_restart(database_path):
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
    game_id = imported_id(client)
    payload = {"game_id": game_id, **options}
    assert new_from(client, **{"game_id": payload.pop("game_id"), **payload}).status_code == 422


def test_chess960_games_cannot_be_played_from_yet(client):
    do_import(client, FISCHER)
    game = client.get("/api/games").json()["games"][0]
    assert game["chess960"] is True
    assert new_from(client, game["game_id"]).status_code == 422


def test_active_game_cannot_be_played_from(client):
    active = start(client)["state"]["game_id"]
    assert new_from(client, active).status_code == 422


def test_starting_with_nothing_is_refused(client):
    body = {"color": "white", "level": "club", "pace": "instant", "time_control": "none"}
    assert client.post("/api/games", json=body).status_code == 422


def test_review_of_a_saved_game_has_every_position(client):
    game_id = imported_id(client)
    body = client.get(f"/api/games/{game_id}/review").json()
    assert body["start_fen"].startswith("rnbqkbnr/pppppppp")
    assert [move["san"] for move in body["moves"]] == ["e4", "c6", "d4", "d5", "e5"]
    assert body["moves"][0]["uci"] == "e2e4"
    assert body["moves"][0]["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3")
    assert (body["white"], body["black"], body["result"]) == ("Ana", "Bia", "1-0")
    assert body["chess960"] is False


def test_review_of_a_chess960_game_starts_from_its_position(client):
    do_import(client, FISCHER)
    game_id = client.get("/api/games").json()["games"][0]["game_id"]
    body = client.get(f"/api/games/{game_id}/review").json()
    assert body["start_fen"].startswith("nrkbbrqn")
    assert body["chess960"] is True
    assert len(body["moves"]) == 2


def test_review_of_a_book_line(client):
    repertoires = client.get("/api/repertoires").json()["repertoires"]
    line = next(v for r in repertoires for v in r["variants"] if v["pgn"] == "1. e4 c5 2. c3")
    body = client.get(f"/api/lines/{line['variant_id']}/review").json()
    assert [move["san"] for move in body["moves"]] == ["e4", "c5", "c3"]
    assert body["white"] is None
    assert body["opening"] == "Sicilian Defense: Alapin Variation"


def test_review_of_unknown_or_active_games_is_refused(client):
    active = start(client)["state"]["game_id"]
    assert client.get(f"/api/games/{active}/review").status_code == 404
    assert client.get("/api/games/nope/review").status_code == 404
    assert client.get("/api/lines/nope/review").status_code == 404


def test_no_active_game_at_first(client):
    assert client.get("/api/games/active").json() == {"game": None}


def test_active_game_comes_back_while_the_server_runs(client):
    game_id = start(client, ui={"scoresheet": True})["state"]["game_id"]
    client.post(
        f"/api/games/{game_id}/moves",
        json={"uci": "e2e4", "user_clock_ms": 170_000, "bot_clock_ms": 180_000},
    )
    game = client.get("/api/games/active").json()["game"]
    assert game["state"]["game_id"] == game_id
    assert [move["san"] for move in game["moves"]] == ["e4", "c5"]
    assert game["setup"]["ui"] == {"scoresheet": True}
    assert game["setup"]["time_control"] == "3i2"
    assert game["clocks"] == {"user_ms": 170_000, "bot_ms": 182_000}


def test_game_continues_after_a_restart(database_path):
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
    game_id = start(client, color="black")["state"]["game_id"]
    assert game_id
    first = client.get("/api/games/active").json()["game"]["moves"]
    assert client.get("/api/games/active").json()["game"]["moves"] == first


def test_finished_game_is_kept_with_its_pgn(database_path):
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
    first = start(client)["state"]["game_id"]
    second = start(client)["state"]["game_id"]
    assert client.get("/api/games/active").json()["game"]["state"]["game_id"] == second
    assert first != second


def test_timeout_pgn_says_time_forfeit(client):
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
    assert clock_after_move(TIME_CONTROLS[key], remaining, used, moves_made) == expected


class SlowEngine(FakeEngine):
    def __init__(self, seconds: float) -> None:
        super().__init__()
        self.seconds = seconds

    async def play(self, board, level, max_time_s=None):
        await asyncio.sleep(self.seconds)
        return await super().play(board, level, max_time_s)


def bullet_as_black(client, pace: str) -> dict:
    body = {
        "color": "black",
        "chess960_position": 288,
        "level": "club",
        "pace": pace,
        "time_control": "30s",
    }
    return client.post("/api/games", json=body).json()


def test_the_search_comes_off_the_bots_clock(database_path):
    with app_on(database_path, SlowEngine(0.2)) as client:
        assert bullet_as_black(client, "instant")["bot_move"]["delay_ms"] == 0
        game = client.get("/api/games/active").json()["game"]
        assert 25_000 < game["clocks"]["bot_ms"] <= 29_800


def test_a_search_inside_the_human_delay_costs_only_the_delay(database_path):
    with app_on(database_path, SlowEngine(0.02)) as client:
        delay_ms = bullet_as_black(client, "human")["bot_move"]["delay_ms"]
        game = client.get("/api/games/active").json()["game"]
        assert game["clocks"]["bot_ms"] == 30_000 - delay_ms
