import io
import random
from collections import Counter

import chess
import chess.pgn
import pytest

from app.book.models import BookMoveRow, Variant, index_moves
from app.game.session import (
    GameFinishedError,
    GameSession,
    IllegalMoveError,
    NotYourTurnError,
    Selection,
)


def walk_game(game):
    """Flattens a game with side variations, to test positions that have several book moves."""
    rows = []

    def visit(node, board, ply):
        for child in node.variations:
            rows.append(BookMoveRow(board.epd(), ply + 1, child.move.uci(), board.san(child.move)))
            next_board = board.copy(stack=False)
            next_board.push(child.move)
            visit(child, next_board, ply + 1)

    visit(game, game.board(), 0)
    return rows


def variant(variant_id, pgn):
    game = chess.pgn.read_game(io.StringIO(pgn + " *"))
    final_epd = game.end().board().epd()
    moves, positions = index_moves(walk_game(game), final_epd)
    return Variant(
        variant_id=variant_id,
        repertoire_id="r",
        names={"en": variant_id},
        eco=None,
        opening=None,
        source="test",
        pgn=pgn,
        moves=moves,
        positions=positions,
        final_epd=final_epd,
    )


def session(*variants, color=chess.WHITE, seed=1):
    return GameSession(
        "g", Selection(variants), color, "none", None, "club", "instant", random.Random(seed)
    )


def bot_plays(game):
    """Plays the bot's book move and returns its SAN, or None if the engine must take over."""
    book_move = game.next_book_move()
    if book_move is None:
        return None
    game.play_bot_move(chess.Move.from_uci(book_move.uci), "book")
    return book_move.san


ROSSOLIMO = "1. e4 c5 2. Nf3 Nc6 3. Bb5"
ALAPIN = "1. e4 c5 2. c3"
VIENNA = "1. e4 e5 2. Nc3"


def test_bot_follows_the_drawn_variation():
    game = session(variant("a", ROSSOLIMO), variant("b", VIENNA))
    game.play_user_move("e2e4")
    expected = "c5" if game.variant.variant_id == "a" else "e5"
    assert bot_plays(game) == expected


def test_each_selected_variation_has_the_same_chance():
    selected = [variant("a", VIENNA), variant("b", ROSSOLIMO), variant("c", ALAPIN)]
    draws = Counter(session(*selected, seed=seed).variant.variant_id for seed in range(3000))
    assert all(900 < count < 1100 for count in draws.values()), draws


def test_rav_branches_are_random():
    line = variant("a", "1. e4 c5 (1... e5) (1... c6)")
    played = set()
    for seed in range(50):
        game = session(line, seed=seed)
        game.play_user_move("e2e4")
        played.add(bot_plays(game))
    assert played == {"c5", "e5", "c6"}


def test_playing_another_selected_variation_is_not_a_deviation_and_redraws():
    rossolimo, alapin = variant("a", ROSSOLIMO), variant("b", ALAPIN)
    for seed in range(20):
        game = session(rossolimo, alapin, seed=seed)
        game.play_user_move("e2e4")
        assert bot_plays(game) == "c5"
        _, deviation = game.play_user_move("c2c3")
        assert deviation is None
        assert game.in_theory
        assert game.next_book_move() is None
        assert game.variant.variant_id == "b"


def test_move_from_unselected_variation_is_a_deviation_with_expected_moves():
    game = session(variant("a", ROSSOLIMO))
    game.play_user_move("e2e4")
    bot_plays(game)
    _, deviation = game.play_user_move("c2c3")
    assert deviation.ply == 3
    assert deviation.played_san == "c3"
    assert deviation.expected_san == ("Nf3",)
    assert not game.in_theory
    assert game.theory_until_ply == 2
    assert game.left_theory_at_move == 2
    assert game.deviations == [deviation]


def test_expected_lists_all_selected_moves():
    game = session(variant("a", ROSSOLIMO), variant("b", ALAPIN))
    game.play_user_move("e2e4")
    bot_plays(game)
    _, deviation = game.play_user_move("d2d4")
    assert set(deviation.expected_san) == {"Nf3", "c3"}


def test_end_of_theory_is_not_a_deviation():
    game = session(variant("a", "1. e4 c5"))
    game.play_user_move("e2e4")
    bot_plays(game)
    _, deviation = game.play_user_move("g1f3")
    assert deviation is None
    assert not game.in_theory
    assert game.deviations == []
    assert game.theory_until_ply == 2


def test_after_deviation_bot_uses_engine_and_game_never_returns_to_theory():
    game = session(variant("a", "1. e4 c5 2. Nf3 d6"))
    game.play_user_move("d2d4")
    assert game.next_book_move() is None
    game.play_bot_move(chess.Move.from_uci("d7d5"), "engine")
    assert not game.in_theory


def test_engine_takes_over_when_drawn_variation_ends_even_if_another_continues():
    short, long = variant("a", "1. e4 c5"), variant("b", "1. e4 c5 2. Nf3 Nc6 3. Bb5")
    game = session(short, long)
    game.variant = long
    game.play_user_move("e2e4")
    bot_plays(game)
    game.play_user_move("g1f3")
    assert game.next_book_move().san == "Nc6"

    game = session(short, long)
    game.variant = variant("c", "1. e4 c5 2. Nf3")
    game.play_user_move("e2e4")
    assert game.next_book_move().san == "c5"
    game.play_bot_move(chess.Move.from_uci("c7c5"), "book")
    game.play_user_move("g1f3")
    assert game.next_book_move() is None


def test_engine_move_outside_theory_leaves_theory_without_deviation():
    game = session(variant("a", "1. e4"))
    game.play_user_move("e2e4")
    assert game.next_book_move() is None
    game.play_bot_move(chess.Move.from_uci("e7e5"), "engine")
    assert not game.in_theory
    assert game.deviations == []
    assert game.theory_until_ply == 1


def test_engine_move_inside_selected_theory_stays_in_theory():
    short, long = variant("a", "1. e4"), variant("b", "1. e4 c5 2. Nf3")
    game = session(short, long)
    game.variant = short
    game.play_user_move("e2e4")
    assert game.next_book_move() is None
    game.play_bot_move(chess.Move.from_uci("c7c5"), "engine")
    assert game.in_theory
    assert game.theory_until_ply == 2


def test_user_move_outside_book_at_move_one_leaves_theory():
    game = session(variant("a", "1. d4 d5 2. c4 e6 3. Nc3"))
    game.play_user_move("c2c4")
    assert not game.in_theory


def test_transposed_position_counts_when_reached_by_book_moves():
    line = variant("a", "1. e4 c6 2. d4 d5 3. Nd2 (3. Nc3 dxe4 4. Nxe4) 3... dxe4 4. Nxe4 Bf5")
    game = session(line, color=chess.BLACK)
    for bot, user in [("e2e4", "c7c6"), ("d2d4", "d7d5"), ("b1c3", "d5e4")]:
        game.play_bot_move(chess.Move.from_uci(bot), "book")
        game.play_user_move(user)
    assert bot_plays(game) == "Nxe4"
    _, deviation = game.play_user_move("c8f5")
    assert deviation is None
    assert game.in_theory


def test_illegal_move_and_wrong_turn_are_rejected():
    game = session(variant("a", VIENNA))
    with pytest.raises(IllegalMoveError):
        game.play_user_move("e2e5")
    with pytest.raises(IllegalMoveError):
        game.play_user_move("nonsense")
    game.play_user_move("e2e4")
    with pytest.raises(NotYourTurnError):
        game.play_user_move("e7e5")


def test_promotion_uses_uci_suffix():
    game = session(variant("a", VIENNA))
    game.board = chess.Board("8/P6k/8/8/8/8/8/K7 w - - 0 1")
    record, _ = game.play_user_move("a7a8n")
    assert record.san == "a8=N"
    assert game.board.piece_at(chess.A8).piece_type == chess.KNIGHT


def test_checkmate_and_result_for_user():
    game = session(variant("a", VIENNA), color=chess.BLACK)
    for bot, user in [("f2f3", "e7e5"), ("g2g4", "d8h4")]:
        game.play_bot_move(chess.Move.from_uci(bot), "engine")
        game.play_user_move(user)
    assert game.outcome.result == "win"
    assert game.outcome.termination == "checkmate"
    assert game.result_tag() == "0-1"
    with pytest.raises(GameFinishedError):
        game.play_bot_move(chess.Move.from_uci("a2a3"), "engine")


def test_threefold_repetition_is_an_automatic_draw():
    game = session(variant("a", VIENNA))
    for _ in range(2):
        for user, bot in [("g1f3", "g8f6"), ("f3g1", "f6g8")]:
            game.play_user_move(user)
            game.play_bot_move(chess.Move.from_uci(bot), "engine")
    assert game.outcome.result == "draw"
    assert game.outcome.termination == "threefold_repetition"


def test_resign_is_a_loss():
    game = session(variant("a", VIENNA))
    game.resign()
    assert game.outcome.result == "loss"
    assert game.result_tag() == "0-1"
    assert game.is_over


def test_flag_loss_win_and_insufficient_material():
    game = session(variant("a", VIENNA))
    game.flag("user", 0)
    assert (game.outcome.result, game.outcome.termination) == ("loss", "timeout")

    game = session(variant("a", VIENNA))
    game.flag("bot", 0)
    assert game.outcome.result == "win"

    game = session(variant("a", VIENNA))
    game.board = chess.Board("8/8/8/4k3/8/8/4K3/8 w - - 0 1")
    game.flag("user", 0)
    assert (game.outcome.result, game.outcome.termination) == (
        "draw",
        "timeout_insufficient_material",
    )


def test_flag_drops_moves_the_browser_never_showed():
    game = session(variant("a", VIENNA))
    game.play_user_move("e2e4")
    game.play_bot_move(chess.Move.from_uci("e7e5"), "book")
    game.flag("bot", 1)
    assert game.ply == 1
    assert game.outcome.result == "win"


def test_pgn_and_lichess_url():
    game = session(variant("a", VIENNA))
    game.play_user_move("e2e4")
    game.play_bot_move(chess.Move.from_uci("e7e5"), "book")
    game.play_user_move("b1c3")
    game.resign()
    assert '[White "You"]' in game.pgn()
    assert '[Result "0-1"]' in game.pgn()
    assert "1. e4 e5 2. Nc3" in game.pgn()
    assert game.lichess_url() == "https://lichess.org/analysis/pgn/e4_e5_Nc3?color=white"


def test_lichess_url_strips_check_signs_and_encodes_promotion():
    game = session(variant("a", VIENNA))
    game.board = chess.Board("6k1/P7/8/8/8/8/8/K7 w - - 0 1")
    game.play_user_move("a7a8q")
    assert game.lichess_url().endswith("/a8%3DQ?color=white")
