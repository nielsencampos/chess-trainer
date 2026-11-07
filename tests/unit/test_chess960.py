import io

import chess
import chess.pgn

SWAP_FEN = "bbqnrkrn/pppppppp/8/8/8/8/PPPPPPPP/BBQNRKRN w KQkq - 0 1"
SWAP_POSITION = 288


def new_game(client, color="white", position=SWAP_POSITION):
    return client.post(
        "/api/games",
        json={
            "color": color,
            "chess960_position": position,
            "level": "club",
            "pace": "instant",
            "time_control": "none",
        },
    )


def test_the_dice_returns_a_starting_position(client):
    body = client.post("/api/chess960", json={}).json()
    board = chess.Board(body["fen"], chess960=True)
    assert board.chess960_pos() == body["position"]


def test_a_starting_fen_is_accepted_in_both_castling_notations(client):
    for fen in (SWAP_FEN, SWAP_FEN.replace("KQkq", "GEge")):
        body = client.post("/api/chess960", json={"fen": fen}).json()
        assert body == {"position": SWAP_POSITION, "fen": SWAP_FEN}


def test_any_other_fen_is_refused(client):
    for fen in (
        "nonsense",
        "",
        SWAP_FEN.replace(" w ", " b "),  # not the first move
        SWAP_FEN.replace("KQkq", "-"),  # no castling rights
        "r1bqkbnr/pppppppp/2n5/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",  # a game in progress
    ):
        assert client.post("/api/chess960", json={"fen": fen}).status_code == 422


def test_a_position_outside_the_960_is_refused(client):
    assert new_game(client, position=960).status_code == 422


def test_a_chess960_game_has_no_opening_lines(client):
    response = client.post(
        "/api/games",
        json={
            "color": "white",
            "chess960_position": 0,
            "variant_ids": ["anything"],
            "level": "club",
            "pace": "instant",
            "time_control": "none",
        },
    )
    assert response.status_code == 422


def test_the_game_starts_out_of_theory_from_the_position(client):
    state = new_game(client).json()["state"]
    assert state["fen"] == SWAP_FEN
    assert state["in_theory"] is False
    assert state["left_theory_at_move"] is None


def test_the_engine_opens_when_the_user_is_black(client):
    body = new_game(client, color="black").json()
    assert body["bot_move"]["source"] == "engine"


def test_castling_is_king_takes_rook_and_is_saved_in_the_pgn(client):
    game_id = new_game(client).json()["state"]["game_id"]
    body = client.post(f"/api/games/{game_id}/moves", json={"uci": "f1g1"}).json()
    assert body["user_move"]["san"] == "O-O"
    assert body["deviation"] is None
    assert body["bot_move"]["source"] == "engine"

    summary = client.post(f"/api/games/{game_id}/resign").json()
    game = chess.pgn.read_game(io.StringIO(summary["pgn"]))
    assert game is not None and not game.errors
    assert game.headers["FEN"] == SWAP_FEN
    assert game.headers["Variant"] == "Chess960"
    assert "VariantId" not in game.headers
    board = game.board()
    assert board.chess960
    first = next(iter(game.mainline_moves()))
    assert board.san(first) == "O-O"


def test_a_finished_game_is_listed_as_chess960_and_can_be_reviewed(client):
    game_id = new_game(client).json()["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "f1g1"})
    client.post(f"/api/games/{game_id}/resign")
    review = client.get(f"/api/games/{game_id}/review").json()
    assert review["chess960"] is True
    assert review["start_fen"] == SWAP_FEN
    assert review["moves"][0]["san"] == "O-O"
    listed = next(g for g in client.get("/api/games").json()["games"] if g["game_id"] == game_id)
    assert listed["chess960"] is True


def test_the_active_game_reports_its_position(client):
    game_id = new_game(client).json()["state"]["game_id"]
    client.post(f"/api/games/{game_id}/moves", json={"uci": "f1g1"})
    active = client.get("/api/games/active").json()["game"]
    assert active["setup"]["chess960"] == {"position": SWAP_POSITION, "fen": SWAP_FEN}
    assert active["moves"][0]["san"] == "O-O"
