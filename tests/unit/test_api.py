"""The HTTP API with the fake engine: setup, moves, clocks, theory, take-back and exports."""

import pytest

SHORT_PGN = "1. e4 c6 2. d4 d5 3. e5 Bf5 4. Nf3"
ALAPIN_PGN = "1. e4 c5 2. c3"


@pytest.fixture
def ids(client):
    """Line id by PGN, from the API.

    Args:
        client (TestClient): The API client.

    Returns:
        dict[str, str]: PGN -> line id.
    """
    repertoires = client.get("/api/repertoires").json()["repertoires"]
    return {v["pgn"]: v["variant_id"] for r in repertoires for v in r["variants"]}


def new_game(client, ids, color="black", pgn=SHORT_PGN, pace="instant", time_control="none"):
    """Starts a game through the API.

    Args:
        client (TestClient): The API client.
        ids (dict[str, str]): Line id by PGN.
        color (str): The user's color.
        pgn (str): The line to select.
        pace (str): The bot's pace.
        time_control (str): The time control's key.

    Returns:
        Response: The API's response.
    """
    return client.post(
        "/api/games",
        json={
            "color": color,
            "variant_ids": [ids[pgn]],
            "level": "club",
            "pace": pace,
            "time_control": time_control,
        },
    )


def test_health_reports_engine(client):
    """The health endpoint reports the engine.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["engine"] == {"name": "Fake Engine 1", "build_tag": "fake"}


def test_serves_frontend_index(client):
    """The frontend's index page is served at `/`.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_repertoires_are_all_catalog_families(client):
    """Repertoires are all catalog families.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    repertoires = client.get("/api/repertoires").json()["repertoires"]
    assert len(repertoires) == 122
    assert sum(len(r["variants"]) for r in repertoires) == 3865
    caro = next(r for r in repertoires if r["names"]["en"] == "Caro-Kann Defense")
    assert len(caro["variants"]) == 110
    assert (caro["group"], caro["order"]) == ("kings-pawn", 3)
    assert repertoires[0]["names"]["en"] == "Sicilian Defense"
    groups = [repertoire["group"] for repertoire in repertoires]
    assert groups == sorted(groups, key=["kings-pawn", "queens-pawn", "flank", "others"].index)
    line = next(v for v in caro["variants"] if v["pgn"] == SHORT_PGN)
    assert line["subgroup"]["en"] == "Advance Variation"
    assert line["eco"] == "B12"
    assert line["opening"] == "Caro-Kann Defense: Advance Variation, Short Variation"
    assert line["names"]["en"] == "Advance Variation, Short Variation"


def test_levels(client):
    """The levels endpoint lists the four levels, weakest first.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert client.get("/api/engine/levels").json()["levels"] == [
        "warmup",
        "club",
        "strong",
        "max",
    ]


def test_time_controls_are_grouped(client):
    """Time controls are grouped.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    body = client.get("/api/time-controls").json()
    groups = {group["key"]: group for group in body["groups"]}
    assert list(groups) == ["bullet", "blitz", "rapid", "classical"]
    bullet = groups["bullet"]["items"]
    assert [item["key"] for item in bullet] == ["30s", "1", "2"]
    assert [item["base_ms"] for item in bullet] == [30_000, 60_000, 120_000]
    assert all(item["increment_ms"] == item["delay_ms"] == 0 for item in bullet)
    assert [item["key"] for item in groups["blitz"]["items"]] == ["5", "10", "3i2", "5u2"]
    assert [item["key"] for item in groups["rapid"]["items"]] == ["25", "25i10", "25d10", "25u5"]
    assert len(groups["classical"]["items"]) == 13
    main = next(item for item in groups["classical"]["items"] if item["key"] == "90+30i30")
    assert main == {
        "key": "90+30i30",
        "base_ms": 5_400_000,
        "increment_ms": 30_000,
        "periods": [{"after_moves": 40, "add_ms": 1_800_000}],
        "delay_ms": 0,
        "delay_kind": None,
    }
    three = next(item for item in groups["classical"]["items"] if item["key"] == "120+60+15d30")
    assert three["periods"] == [
        {"after_moves": 40, "add_ms": 3_600_000},
        {"after_moves": 60, "add_ms": 900_000},
    ]
    assert (three["delay_ms"], three["delay_kind"]) == (30_000, "bronstein")
    assert all(set(group) == {"key", "items"} for group in body["groups"])
    assert body["no_clock"] == "none"
    assert body["default"] == "25i10"


def test_every_time_control_starts_a_game(client, ids):
    """Every time control starts a game.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    body = client.get("/api/time-controls").json()
    keys = [item["key"] for group in body["groups"] for item in group["items"]] + ["none"]
    for key in keys:
        assert new_game(client, ids, time_control=key).status_code == 201, key


def test_engine_search_is_limited_by_the_bots_clock(client, ids, engine):
    """Engine search is limited by the bot's clock.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
        engine (FakeEngine): The fake engine the client uses.
    """
    game_id = new_game(client, ids, color="white", pgn=ALAPIN_PGN, time_control="5")
    game_id = game_id.json()["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4", "bot_clock_ms": 30_000})
    client.post(f"/api/games/{game_id}/moves", json={"uci": "c2c3", "bot_clock_ms": 30_000})
    assert engine.calls == 1
    assert engine.last_max_time_s == pytest.approx(1.0)


def test_no_clock_does_not_limit_the_engine(client, ids, engine):
    """No clock does not limit the engine.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
        engine (FakeEngine): The fake engine the client uses.
    """
    game_id = new_game(client, ids, color="white", pgn=ALAPIN_PGN).json()["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4"})
    client.post(f"/api/games/{game_id}/moves", json={"uci": "c2c3"})
    assert engine.calls == 1
    assert engine.last_max_time_s is None


def test_classical_pgn_records_the_bonus(client, ids):
    """Classical PGN records the bonus.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    game_id = new_game(client, ids, time_control="90+30i30").json()["state"]["game_id"]
    summary = client.post(f"/api/games/{game_id}/resign").json()
    assert '[TimeControl "40/5400+30:1800+30"]' in summary["pgn"]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("3i2", "180+2"),
        ("60", "3600+0"),
        ("120+60+30", "40/7200+0:20/3600+0:1800+0"),
        ("25d10", "1500d10"),
        ("115+60u5", "40/6900us5:3600us5"),
    ],
)
def test_pgn_time_control_tags(client, ids, key, expected):
    """PGN time control tags.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
        key (str): A time control key.
        expected (str): Its PGN `TimeControl` tag.
    """
    game_id = new_game(client, ids, time_control=key).json()["state"]["game_id"]
    summary = client.post(f"/api/games/{game_id}/resign").json()
    assert f'[TimeControl "{expected}"]' in summary["pgn"]


def test_opening_name_comes_with_each_move_and_carries_forward(client, ids, engine):
    """Opening name comes with each move and carries forward.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
        engine (FakeEngine): The fake engine the client uses.
    """
    game = new_game(client, ids, color="white", pgn=ALAPIN_PGN).json()
    assert game["state"]["opening"] is None
    game_id = game["state"]["game_id"]

    body = client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4"}).json()
    assert body["user_move"]["opening"]["name"] == "King's Pawn Game"
    assert body["bot_move"]["opening"] == {"eco": "B20", "name": "Sicilian Defense"}

    engine.script = ["Nc6"]
    body = client.post(f"/api/games/{game_id}/moves", json={"uci": "c2c3"}).json()
    assert body["user_move"]["opening"]["name"] == "Sicilian Defense: Alapin Variation"

    engine.script = ["h6"]
    body = client.post(f"/api/games/{game_id}/moves", json={"uci": "h2h3"}).json()
    # Not a named position: the last name stays.
    assert body["bot_move"]["opening"]["name"].startswith("Sicilian Defense")
    assert body["state"]["opening"] == body["bot_move"]["opening"]


def test_new_game_as_black_gets_bot_first_move(client, ids):
    """New game as black gets bot first move.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    response = new_game(client, ids)
    assert response.status_code == 201
    body = response.json()
    assert body["bot_move"]["san"] == "e4"
    assert body["bot_move"]["source"] == "book"
    assert body["state"]["ply"] == 1


def test_new_game_as_white_waits_for_the_user(client, ids):
    """New game as white waits for the user.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    body = new_game(client, ids, color="white", pgn=ALAPIN_PGN).json()
    assert body["bot_move"] is None
    assert body["state"]["ply"] == 0


def test_same_line_plays_with_either_color(client, ids):
    """Same line plays with either color.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    assert new_game(client, ids, color="white", pgn=SHORT_PGN).status_code == 201
    assert new_game(client, ids, color="black", pgn=SHORT_PGN).status_code == 201


@pytest.mark.parametrize(
    "overrides",
    [
        {"variant_ids": []},
        {"variant_ids": ["nope"]},
        {"level": "nope"},
        {"time_control": "10+5"},
        {"time_control": "45+30"},
        {"pace": "slow"},
        {"color": "red"},
    ],
)
def test_invalid_setup_is_rejected(client, ids, overrides):
    """Invalid setup is rejected.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
        overrides (dict): Fields that make the setup invalid.
    """
    payload = {
        "color": "black",
        "variant_ids": [ids[SHORT_PGN]],
        "level": "club",
        "pace": "instant",
        "time_control": "none",
    }
    assert client.post("/api/games", json={**payload, **overrides}).status_code == 422


def test_every_line_selected_starts_a_game(client, ids):
    """Every line selected starts a game.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    response = client.post(
        "/api/games",
        json={
            "color": "white",
            "variant_ids": list(ids.values()),
            "level": "club",
            "pace": "instant",
            "time_control": "none",
        },
    )
    assert response.status_code == 201
    game_id = response.json()["state"]["game_id"]
    body = client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4"}).json()
    assert body["deviation"] is None
    assert body["state"]["in_theory"] is True


def test_full_flow_book_then_deviation_then_engine(client, ids, engine):
    """Full flow book then deviation then engine.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
        engine (FakeEngine): The fake engine the client uses.
    """
    game_id = new_game(client, ids).json()["state"]["game_id"]

    body = client.post(f"/api/games/{game_id}/moves", json={"uci": "c7c6"}).json()
    assert body["user_move"]["san"] == "c6"
    assert body["deviation"] is None
    assert body["bot_move"]["san"] == "d4"
    assert body["state"]["in_theory"] is True

    engine.script = ["Nc3"]
    body = client.post(f"/api/games/{game_id}/moves", json={"uci": "e7e6"}).json()
    assert body["deviation"]["played_san"] == "e6"
    assert body["deviation"]["expected_san"] == ["d5"]
    assert body["deviation"]["move_number"] == 2
    assert body["bot_move"]["source"] == "engine"
    assert body["bot_move"]["san"] == "Nc3"
    assert body["state"]["in_theory"] is False
    assert body["state"]["left_theory_at_move"] == 2

    summary = client.post(f"/api/games/{game_id}/resign").json()
    assert summary["result"] == "loss"
    assert summary["termination"] == "resignation"
    assert summary["state"]["theory_until_ply"] == 3
    assert summary["variant_id"] == ids[SHORT_PGN]
    assert summary["eco"] == "B12"
    assert summary["deviations"][0]["expected_san"] == ["d5"]
    assert "1. e4 c6 2. d4 e6 { Deviation: expected d5 } 3. Nc3" in summary["pgn"]
    assert "lichess_url" not in summary


def test_human_pace_returns_a_delay(client, ids):
    """Human pace returns a delay.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    bot_move = new_game(client, ids, pace="human", time_control="90+30i30").json()["bot_move"]
    assert 9_000 <= bot_move["delay_ms"] <= 27_000


def test_instant_pace_has_no_delay(client, ids):
    """Instant pace has no delay.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    assert new_game(client, ids).json()["bot_move"]["delay_ms"] == 0


def test_illegal_move_unknown_game_and_finished_game(client, ids):
    """Illegal move unknown game and finished game.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    game_id = new_game(client, ids).json()["state"]["game_id"]
    assert client.post(f"/api/games/{game_id}/moves", json={"uci": "e7e4"}).status_code == 422
    assert client.post("/api/games/nope/moves", json={"uci": "e7e5"}).status_code == 404
    assert client.get("/api/games/nope").status_code == 404
    client.post(f"/api/games/{game_id}/resign")
    assert client.post(f"/api/games/{game_id}/moves", json={"uci": "c7c6"}).status_code == 409
    assert client.post(f"/api/games/{game_id}/resign").status_code == 409


def test_timeout_endpoint(client, ids):
    """The timeout endpoint ends the game as a loss on time.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    game_id = new_game(client, ids, time_control="3i2").json()["state"]["game_id"]
    body = client.post(
        f"/api/games/{game_id}/timeout", json={"side": "user", "shown_plies": 1}
    ).json()
    assert body["result"] == "loss"
    assert body["termination"] == "timeout"


def test_get_game_returns_moves_with_sources(client, ids):
    """Get game returns moves with sources.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    game_id = new_game(client, ids).json()["state"]["game_id"]
    body = client.get(f"/api/games/{game_id}").json()
    assert body["result"] is None
    assert body["moves"] == [
        {"ply": 1, "san": "e4", "by": "bot", "source": "book", "in_theory": True}
    ]


def test_export_lines_in_book_order(client, ids):
    """Export lines in book order.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    wanted = [ids[ALAPIN_PGN], ids[SHORT_PGN]]
    response = client.post("/api/lines/export", json={"variant_ids": wanted})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-chess-pgn")
    text = response.text
    assert text.count('[Event "chess-trainer"]') == 2
    assert "1. e4 c5 2. c3 *" in text
    assert "1. e4 c6 2. d4 d5 3. e5 Bf5 4. Nf3 *" in text
    assert '[ECO "B' in text


def test_export_lines_refuses_unknown_and_empty(client):
    """Export lines refuses unknown and empty.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert client.post("/api/lines/export", json={"variant_ids": []}).status_code == 422
    assert client.post("/api/lines/export", json={"variant_ids": ["nope"]}).status_code == 422


def test_bullet_game_records_its_time_control(client, ids):
    """Bullet game records its time control.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    state = new_game(client, ids, color="white", time_control="30s").json()["state"]
    summary = client.post(f"/api/games/{state['game_id']}/resign").json()
    assert '[TimeControl "30+0"]' in summary["pgn"]


def test_take_back_restores_position_theory_and_clocks(client, ids):
    """Take back restores position theory and clocks.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    state = new_game(client, ids, color="white", pgn=ALAPIN_PGN, time_control="5").json()["state"]
    game_id = state["game_id"]
    body = {"uci": "d2d4", "user_clock_ms": 290_000, "bot_clock_ms": 300_000}
    moved = client.post(f"/api/games/{game_id}/moves", json=body).json()
    assert moved["deviation"] is not None
    back = client.post(
        f"/api/games/{game_id}/takeback",
        json={"shown_plies": 1, "user_clock_ms": 299_000, "bot_clock_ms": 300_000},
    )
    assert back.status_code == 200
    assert back.json()["ply"] == 0
    assert back.json()["in_theory"] is True
    active = client.get("/api/games/active").json()["game"]
    assert active["moves"] == []
    assert active["clocks"] == {"user_ms": 299_000, "bot_ms": 300_000}
    summary = client.post(f"/api/games/{game_id}/resign").json()
    assert summary["deviations"] == []
    assert summary["pgn"].split("\n\n")[-1] == "0-1"  # no moves left


def test_take_back_refuses_a_shown_reply_and_a_finished_game(client, ids):
    """Take back refuses a shown reply and a finished game.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    game_id = new_game(client, ids, color="white", pgn=ALAPIN_PGN).json()["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4"})
    url = f"/api/games/{game_id}/takeback"
    assert client.post(url, json={"shown_plies": 2}).status_code == 409
    assert client.post(url, json={"shown_plies": 0}).status_code == 422
    client.post(f"/api/games/{game_id}/resign")
    assert client.post(url, json={"shown_plies": 1}).status_code == 409


def test_evaluate_reports_whites_side_and_finished_positions(client, engine):
    """Evaluate reports White's side and finished positions.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        engine (FakeEngine): The fake engine the client uses.
    """
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    body = client.post("/api/evaluate", json={"fen": start}).json()
    assert body["cp"] == 0 and body["mate"] is None and body["best"]
    up_a_knight = "rnbqkb1r/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1"
    assert client.post("/api/evaluate", json={"fen": up_a_knight}).json()["cp"] == 300
    calls = engine.evaluations
    client.post("/api/evaluate", json={"fen": up_a_knight})
    assert engine.evaluations == calls  # cached
    mated = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
    assert client.post("/api/evaluate", json={"fen": mated}).json() == {
        "cp": -10_000,
        "mate": 0,
        "best": None,
    }


def test_evaluate_refuses_an_invalid_position(client):
    """Evaluate refuses an invalid position.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    assert client.post("/api/evaluate", json={"fen": "nonsense"}).status_code == 422
    no_kings = "8/8/8/8/8/8/8/8 w - - 0 1"
    assert client.post("/api/evaluate", json={"fen": no_kings}).status_code == 422


def test_reviews_mark_book_moves_and_the_deviation(client, ids):
    """Reviews mark book moves and the deviation.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        ids (dict[str, str]): Line id by PGN, from the API.
    """
    game_id = new_game(client, ids, color="white", pgn=ALAPIN_PGN).json()["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4"})
    client.post(f"/api/games/{game_id}/moves", json={"uci": "d2d4"})  # 2. c3 is the book
    client.post(f"/api/games/{game_id}/resign")
    moves = client.get(f"/api/games/{game_id}/review").json()["moves"]
    assert [(m["san"], m["book"], m["deviation"]) for m in moves[:3]] == [
        ("e4", True, False),
        ("c5", True, False),
        ("d4", False, True),
    ]
    line = client.get(f"/api/lines/{ids[ALAPIN_PGN]}/review").json()["moves"]
    assert all(move["book"] for move in line)
