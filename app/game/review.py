"""Turns a PGN into the positions of a read-only review. Works for Chess960 too."""

import io

import chess.pgn

from app.book.models import Variant


def review_of_pgn(pgn: str) -> dict | None:
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None or game.errors:
        return None
    board = game.board()
    start_fen = board.fen()
    moves = []
    for ply, move in enumerate(game.mainline_moves(), 1):
        san = board.san(move)
        board.push(move)
        moves.append({"ply": ply, "san": san, "uci": move.uci(), "fen": board.fen()})
    return {"start_fen": start_fen, "moves": moves}


def pgn_of_line(variant: Variant) -> str:
    """A book line as a PGN game, ready to export."""
    game = chess.pgn.read_game(io.StringIO(f"{variant.pgn} *"))
    if game is None or game.errors:
        raise ValueError(f"line {variant.variant_id} has an invalid PGN")
    game.headers["Event"] = "chess-trainer"
    game.headers["Site"] = "local"
    if variant.eco:
        game.headers["ECO"] = variant.eco
    if variant.opening:
        game.headers["Opening"] = variant.opening
    return str(game)
