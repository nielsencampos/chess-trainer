"""Turns a PGN into the positions of a read-only review. Works for Chess960 too."""

import io

import chess.pgn


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
