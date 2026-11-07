import chess
import pytest

from app.book.loader import BookError, load_book

HEADERS = """[RepertoireId "r"]
[RepertoireName_en "R"]
[VariantId "{vid}"]
[Color "{color}"]
[Name_en "{name}"]
[Source "test"]
"""


def write(tmp_path, *games, filename="r.pgn"):
    (tmp_path / filename).write_text("\n".join(games), encoding="utf-8")
    return tmp_path


def game(moves, vid="r.a", color="black", name="A"):
    return HEADERS.format(vid=vid, color=color, name=name) + f"\n{moves} *\n"


def test_loads_variant_and_repertoire(tmp_path):
    book = load_book(write(tmp_path, game("1. e4 c6 2. d4")))
    variant = book.variants["r.a"]
    assert variant.moves_san == ("e4", "c6", "d4")
    assert variant.names == {"en": "A"}
    assert book.repertoires["r"].names == {"en": "R"}
    assert book.repertoires["r"].variant_ids == ("r.a",)


def test_final_position_is_in_positions_without_moves(tmp_path):
    variant = load_book(write(tmp_path, game("1. e4 c6"))).variants["r.a"]
    assert variant.final_epd in variant.positions
    assert variant.final_epd not in variant.moves


def test_rav_becomes_book_branch(tmp_path):
    variant = load_book(write(tmp_path, game("1. e4 c6 (1... e5 2. Nf3) 2. d4"))).variants["r.a"]
    board = chess.Board()
    board.push_san("e4")
    assert {move.san for move in variant.moves[board.epd()]} == {"c6", "e5"}
    board.push_san("e5")
    assert [move.san for move in variant.moves[board.epd()]] == ["Nf3"]
    assert variant.moves_san == ("e4", "c6", "d4")


def test_rav_transposition_merges_into_main_line(tmp_path):
    pgn = "1. e4 c6 2. d4 d5 3. Nd2 (3. Nc3 dxe4 4. Nxe4) 3... dxe4 4. Nxe4 Bf5"
    variant = load_book(write(tmp_path, game(pgn))).variants["r.a"]
    board = chess.Board()
    for san in ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4"]:
        board.push_san(san)
    assert [move.san for move in variant.moves[board.epd()]] == ["Bf5"]


@pytest.mark.parametrize(
    ("pgn", "message"),
    [
        (game("1. e4 e4"), "invalid PGN"),
        (game("", vid="r.empty"), "has no moves"),
        (game("1. e4", name=""), "Name_en"),
        (game("1. e4", vid=""), "VariantId"),
        (game("1. e4", color="red"), "Color"),
    ],
)
def test_invalid_game_fails_loudly(tmp_path, pgn, message):
    with pytest.raises(BookError, match=message):
        load_book(write(tmp_path, pgn))


def test_missing_source_fails(tmp_path):
    pgn = game("1. e4").replace('[Source "test"]\n', "")
    with pytest.raises(BookError, match="Source"):
        load_book(write(tmp_path, pgn))


def test_duplicate_variant_id_across_files_fails(tmp_path):
    write(tmp_path, game("1. e4"), filename="a.pgn")
    write(tmp_path, game("1. d4"), filename="b.pgn")
    with pytest.raises(BookError, match="duplicate VariantId"):
        load_book(tmp_path)


def test_mixed_colors_in_repertoire_fail(tmp_path):
    games = [game("1. e4", vid="r.a"), game("1. d4", vid="r.b", color="white")]
    with pytest.raises(BookError, match="mixes colors"):
        load_book(write(tmp_path, *games))


def test_empty_directory_fails(tmp_path):
    with pytest.raises(BookError, match="no .pgn"):
        load_book(tmp_path)
