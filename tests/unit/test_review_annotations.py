"""What the review reads from a PGN: classifications, evaluations, clocks, comments, variations."""

from app.game.review import review_of_pgn

# Shaped like a Chess.com analysis download: NAGs, [%c_effect], [%timestamp] in tenths.
CHESSCOM = """[White "Ana"]
[Black "Bia"]
[TimeControl "180"]
[Result "*"]

1. d4 {[%clk 0:02:59.9][%timestamp 1]} 1... Nf6 {[%clk 0:02:57.7][%timestamp
23]} 2. Bg5 $2 {[%clk 0:02:58.9][%timestamp 10][%c_effect
g5;square;g5;type;Mistake;persistent;true]} 2... Ne4 $9 {[%clk 0:02:55][%timestamp 27]}
3. Bh4 $1 {[%c_effect h4;square;h4;type;GreatFind;persistent;true] keeps the pin}
(3. Bf4 $4 {[%c_effect f4;square;f4;type;Blunder;persistent;true] drops a pawn} 3... e5
(3... d5 $15)) 3... g5 $3 {[%c_effect g5;square;g5;type;Brilliant;size;100%25;persistent;true]} *
"""

# Shaped like a Lichess export with server analysis and literate comments.
LICHESS = """[White "Ana"]
[Black "Bia"]
[TimeControl "300+3"]
[Result "*"]

1. e4 { [%eval 0.18] [%clk 0:05:00] } 1... e5 { [%eval 0.22] [%clk 0:05:00] }
2. f4?! { (0.22 → -0.34) Inaccuracy. Nf3 was best. } { [%eval -0.34] [%clk 0:04:55] }
(2. Nf3 Nc6) 2... exf4 { [%eval #-3] [%clk 0:05:01] } *
"""


def moves_of(pgn):
    review = review_of_pgn(pgn)
    assert review is not None
    return review["moves"]


def test_chesscom_classifications_come_from_the_effect_then_the_nag():
    moves = moves_of(CHESSCOM)
    kinds = [m.get("kind") for m in moves]
    assert kinds == [None, None, "mistake", "miss", "great", "brilliant"]


def test_chesscom_times_come_from_the_timestamp_and_clocks_from_clk():
    first, second = moves_of(CHESSCOM)[:2]
    assert (first["clock_ms"], first["spent_ms"]) == (179_900, 100)
    assert (second["clock_ms"], second["spent_ms"]) == (177_700, 2_300)


def test_comments_lose_their_commands_and_keep_their_text():
    moves = moves_of(CHESSCOM)
    assert "comment" not in moves[0]
    assert moves[4]["comment"] == "keeps the pin"


def test_variations_branch_off_the_move_they_replace_and_nest():
    moves = moves_of(CHESSCOM)
    [side] = moves[4]["variations"]
    assert [(m["ply"], m["san"]) for m in side] == [(5, "Bf4"), (6, "e5")]
    assert (side[0]["kind"], side[0]["comment"]) == ("blunder", "drops a pawn")
    [nested] = side[1]["variations"]
    assert (nested[0]["san"], nested[0]["symbol"]) == ("d5", "⩱")
    assert "clock_ms" not in side[0]
    assert side[1]["fen"].startswith("rnbqkb1r/pppp1ppp/8/4p3/3PnB2/8/PPP1PPPP/RN1QKBNR w")


def test_lichess_evaluations_are_from_whites_side_with_mates():
    moves = moves_of(LICHESS)
    assert moves[0]["eval"] == {"cp": 18, "mate": None}
    assert moves[2]["eval"] == {"cp": -34, "mate": None}
    assert moves[3]["eval"] == {"cp": None, "mate": -3}
    assert moves[2]["kind"] == "inaccuracy"
    assert moves[2]["comment"] == "(0.22 → -0.34) Inaccuracy. Nf3 was best."
    assert [m["san"] for m in moves[2]["variations"][0]] == ["Nf3", "Nc6"]


def test_time_spent_comes_from_two_clocks_and_the_increment():
    moves = moves_of(LICHESS)
    assert moves[0]["spent_ms"] == 3_000  # 5:00 + 3 s increment - 5:00
    assert moves[2]["spent_ms"] == 8_000  # 5:00 + 3 - 4:55
    assert moves[3]["spent_ms"] == 2_000  # 5:00 + 3 - 5:01


def test_a_game_without_annotations_has_only_the_moves():
    moves = moves_of("1. e4 e5 *")
    assert set(moves[0]) == {"ply", "san", "uci", "fen"}
