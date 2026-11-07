import pytest

SHORT = "caro-kann.advance.short"
ALAPIN = "sicilian-alapin.main"


def new_game(client, color="black", variant_ids=(SHORT,), pace="instant", time_control="none"):
    return client.post(
        "/api/games",
        json={
            "color": color,
            "variant_ids": list(variant_ids),
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


def test_repertoires_filter_by_color(client):
    body = client.get("/api/repertoires", params={"color": "black"}).json()
    assert {rep["repertoire_id"] for rep in body["repertoires"]} == {
        "caro-kann",
        "sicilian-taimanov",
    }
    variant = next(
        v for rep in body["repertoires"] for v in rep["variants"] if v["variant_id"] == SHORT
    )
    assert variant["eco"] == "B12"
    assert variant["names"]["en"].startswith("Advance")


def test_levels(client):
    assert client.get("/api/engine/levels").json()["levels"] == [
        "warmup",
        "club",
        "strong",
        "max",
    ]


def test_new_game_as_black_gets_bot_first_move(client):
    response = new_game(client)
    assert response.status_code == 201
    body = response.json()
    assert body["bot_move"]["san"] == "e4"
    assert body["bot_move"]["source"] == "book"
    assert body["state"]["ply"] == 1


def test_new_game_as_white_waits_for_the_user(client):
    body = new_game(client, color="white", variant_ids=[ALAPIN]).json()
    assert body["bot_move"] is None
    assert body["state"]["ply"] == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"variant_ids": []},
        {"variant_ids": ["nope"]},
        {"variant_ids": [ALAPIN]},  # a white variation in a black game
        {"level": "nope"},
        {"time_control": "1+1"},
        {"pace": "slow"},
    ],
)
def test_invalid_setup_is_rejected(client, overrides):
    payload = {
        "color": "black",
        "variant_ids": [SHORT],
        "level": "club",
        "pace": "instant",
        "time_control": "none",
    }
    assert client.post("/api/games", json={**payload, **overrides}).status_code == 422


def test_full_flow_book_then_deviation_then_engine(client, engine):
    game_id = new_game(client).json()["state"]["game_id"]

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
    assert summary["variant_id"] == SHORT
    assert summary["deviations"][0]["expected_san"] == ["d5"]
    assert "1. e4 c6 2. d4 e6 3. Nc3" in summary["pgn"]
    assert "lichess.org/analysis/pgn/e4_c6_d4_e6_Nc3" in summary["lichess_url"]


def test_human_pace_returns_a_delay(client):
    bot_move = new_game(client, pace="human", time_control="45+30").json()["bot_move"]
    assert 4_500 <= bot_move["delay_ms"] <= 15_000


def test_instant_pace_has_no_delay(client):
    assert new_game(client).json()["bot_move"]["delay_ms"] == 0


def test_illegal_move_unknown_game_and_finished_game(client):
    game_id = new_game(client).json()["state"]["game_id"]
    assert client.post(f"/api/games/{game_id}/moves", json={"uci": "e7e4"}).status_code == 422
    assert client.post("/api/games/nope/moves", json={"uci": "e7e5"}).status_code == 404
    assert client.get("/api/games/nope").status_code == 404
    client.post(f"/api/games/{game_id}/resign")
    assert client.post(f"/api/games/{game_id}/moves", json={"uci": "c7c6"}).status_code == 409
    assert client.post(f"/api/games/{game_id}/resign").status_code == 409


def test_timeout_endpoint(client):
    game_id = new_game(client, time_control="3+2").json()["state"]["game_id"]
    body = client.post(
        f"/api/games/{game_id}/timeout", json={"side": "user", "shown_plies": 1}
    ).json()
    assert body["result"] == "loss"
    assert body["termination"] == "timeout"


def test_get_game_returns_moves_with_sources(client):
    game_id = new_game(client).json()["state"]["game_id"]
    body = client.get(f"/api/games/{game_id}").json()
    assert body["result"] is None
    assert body["moves"] == [
        {"ply": 1, "san": "e4", "by": "bot", "source": "book", "in_theory": True}
    ]
