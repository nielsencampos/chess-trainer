import pytest

SHORT_PGN = "1. e4 c6 2. d4 d5 3. e5 Bf5 4. Nf3"
ALAPIN_PGN = "1. e4 c5 2. c3"


@pytest.fixture
def ids(client):
    repertoires = client.get("/api/repertoires").json()["repertoires"]
    return {v["pgn"]: v["variant_id"] for r in repertoires for v in r["variants"]}


def new_game(client, ids, color="black", pgn=SHORT_PGN, pace="instant", time_control="none"):
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
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["engine"] == {"name": "Fake Engine 1", "build_tag": "fake"}


def test_serves_frontend_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_repertoires_are_all_catalog_families(client):
    repertoires = client.get("/api/repertoires").json()["repertoires"]
    assert len(repertoires) == 149
    assert sum(len(r["variants"]) for r in repertoires) == 3865
    caro = next(r for r in repertoires if r["names"]["en"] == "Caro-Kann Defense")
    assert len(caro["variants"]) == 110
    line = next(v for v in caro["variants"] if v["pgn"] == SHORT_PGN)
    assert line["eco"] == "B12"
    assert line["opening"] == "Caro-Kann Defense: Advance Variation, Short Variation"
    assert line["names"]["en"] == "Advance Variation, Short Variation"


def test_levels(client):
    assert client.get("/api/engine/levels").json()["levels"] == [
        "warmup",
        "club",
        "strong",
        "max",
    ]


def test_time_controls_are_grouped_with_scoresheet_only_for_classical(client):
    body = client.get("/api/time-controls").json()
    groups = {group["key"]: group for group in body["groups"]}
    assert [item["key"] for item in groups["bullet"]["items"]] == [
        "20s+1",
        "30s+0",
        "1+0",
        "1+1",
        "2+1",
    ]
    assert [item["key"] for item in groups["blitz"]["items"]] == ["3+0", "3+2", "5+0", "5+3"]
    assert [item["key"] for item in groups["rapid"]["items"]] == [
        "10+0",
        "10+5",
        "15+10",
        "20+0",
        "30+0",
        "60+0",
    ]
    assert groups["classical"]["items"] == [
        {
            "key": "90+30+30",
            "base_ms": 5_400_000,
            "increment_ms": 30_000,
            "moves_to_bonus": 40,
            "bonus_ms": 1_800_000,
        },
        {
            "key": "45+15+15",
            "base_ms": 2_700_000,
            "increment_ms": 15_000,
            "moves_to_bonus": 40,
            "bonus_ms": 900_000,
        },
    ]
    assert [key for key, group in groups.items() if group["scoresheet"]] == ["classical"]
    assert body["no_clock"] == "none"
    assert sum(len(group["items"]) for group in groups.values()) + 1 == 18


def test_every_time_control_starts_a_game(client, ids):
    body = client.get("/api/time-controls").json()
    keys = [item["key"] for group in body["groups"] for item in group["items"]] + ["none"]
    for key in keys:
        assert new_game(client, ids, time_control=key).status_code == 201, key


def test_engine_search_is_limited_by_the_bots_clock(client, ids, engine):
    game_id = new_game(client, ids, color="white", pgn=ALAPIN_PGN, time_control="30s+0")
    game_id = game_id.json()["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4", "bot_clock_ms": 30_000})
    client.post(f"/api/games/{game_id}/moves", json={"uci": "c2c3", "bot_clock_ms": 30_000})
    assert engine.calls == 1
    assert engine.last_max_time_s == pytest.approx(1.0)


def test_no_clock_does_not_limit_the_engine(client, ids, engine):
    game_id = new_game(client, ids, color="white", pgn=ALAPIN_PGN).json()["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "e2e4"})
    client.post(f"/api/games/{game_id}/moves", json={"uci": "c2c3"})
    assert engine.calls == 1
    assert engine.last_max_time_s is None


def test_classical_pgn_records_the_bonus(client, ids):
    game_id = new_game(client, ids, time_control="90+30+30").json()["state"]["game_id"]
    summary = client.post(f"/api/games/{game_id}/resign").json()
    assert '[TimeControl "40/5400+30:1800+30"]' in summary["pgn"]


def test_new_game_as_black_gets_bot_first_move(client, ids):
    response = new_game(client, ids)
    assert response.status_code == 201
    body = response.json()
    assert body["bot_move"]["san"] == "e4"
    assert body["bot_move"]["source"] == "book"
    assert body["state"]["ply"] == 1


def test_new_game_as_white_waits_for_the_user(client, ids):
    body = new_game(client, ids, color="white", pgn=ALAPIN_PGN).json()
    assert body["bot_move"] is None
    assert body["state"]["ply"] == 0


def test_same_line_plays_with_either_color(client, ids):
    assert new_game(client, ids, color="white", pgn=SHORT_PGN).status_code == 201
    assert new_game(client, ids, color="black", pgn=SHORT_PGN).status_code == 201


@pytest.mark.parametrize(
    "overrides",
    [
        {"variant_ids": []},
        {"variant_ids": ["nope"]},
        {"level": "nope"},
        {"time_control": "7+7"},
        {"time_control": "45+30"},
        {"pace": "slow"},
        {"color": "red"},
    ],
)
def test_invalid_setup_is_rejected(client, ids, overrides):
    payload = {
        "color": "black",
        "variant_ids": [ids[SHORT_PGN]],
        "level": "club",
        "pace": "instant",
        "time_control": "none",
    }
    assert client.post("/api/games", json={**payload, **overrides}).status_code == 422


def test_every_line_selected_starts_a_game(client, ids):
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
    assert "1. e4 c6 2. d4 e6 3. Nc3" in summary["pgn"]
    assert "lichess.org/analysis/pgn/e4_c6_d4_e6_Nc3" in summary["lichess_url"]


def test_human_pace_returns_a_delay(client, ids):
    bot_move = new_game(client, ids, pace="human", time_control="90+30+30").json()["bot_move"]
    assert 9_000 <= bot_move["delay_ms"] <= 27_000


def test_instant_pace_has_no_delay(client, ids):
    assert new_game(client, ids).json()["bot_move"]["delay_ms"] == 0


def test_illegal_move_unknown_game_and_finished_game(client, ids):
    game_id = new_game(client, ids).json()["state"]["game_id"]
    assert client.post(f"/api/games/{game_id}/moves", json={"uci": "e7e4"}).status_code == 422
    assert client.post("/api/games/nope/moves", json={"uci": "e7e5"}).status_code == 404
    assert client.get("/api/games/nope").status_code == 404
    client.post(f"/api/games/{game_id}/resign")
    assert client.post(f"/api/games/{game_id}/moves", json={"uci": "c7c6"}).status_code == 409
    assert client.post(f"/api/games/{game_id}/resign").status_code == 409


def test_timeout_endpoint(client, ids):
    game_id = new_game(client, ids, time_control="3+2").json()["state"]["game_id"]
    body = client.post(
        f"/api/games/{game_id}/timeout", json={"side": "user", "shown_plies": 1}
    ).json()
    assert body["result"] == "loss"
    assert body["termination"] == "timeout"


def test_get_game_returns_moves_with_sources(client, ids):
    game_id = new_game(client, ids).json()["state"]["game_id"]
    body = client.get(f"/api/games/{game_id}").json()
    assert body["result"] is None
    assert body["moves"] == [
        {"ply": 1, "san": "e4", "by": "bot", "source": "book", "in_theory": True}
    ]
