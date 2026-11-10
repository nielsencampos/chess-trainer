"""Turns a PGN into the positions of a read-only review. Works for Chess960 too.

Each move carries what the PGN says about it, when it says it: the classification of the site
that analysed it (Lichess or Chess.com NAGs and Chess.com's `[%c_effect]`), its evaluation
(`[%eval]`), the clock after it (`[%clk]`), the time it took, the comment without the commands, and
the side variations that branch off it. Nothing here is computed by an engine.
"""

import io
import re

import chess
import chess.pgn

from app.book.models import Variant

# Chess.com writes the classification it drew on the board; it wins over the NAG.
EFFECT_KINDS = {
    "brilliant": "brilliant",
    "greatfind": "great",
    "best": "best",
    "excellent": "excellent",
    "good": "good",
    "inaccuracy": "inaccuracy",
    "mistake": "mistake",
    "miss": "miss",
    "blunder": "blunder",
}
# $9 is "worst move" in the PGN standard, but Chess.com uses it for a missed win, the only site
# that writes it.
NAG_KINDS = {3: "brilliant", 1: "great", 6: "inaccuracy", 2: "mistake", 9: "miss", 4: "blunder"}
NAG_SYMBOLS = {
    5: "!?",
    7: "□",
    10: "=",
    13: "∞",
    14: "⩲",
    15: "⩱",
    16: "±",
    17: "∓",
    18: "+−",  # noqa: RUF001  the minus sign is the symbol
    19: "−+",  # noqa: RUF001
}
COMMAND = re.compile(r"\[%[^\]]*\]")
EFFECT_TYPE = re.compile(r"\[%c_effect[^\]]*?;type;([A-Za-z]+)")
TIMESTAMP = re.compile(r"\[%timestamp\s+(\d+)\]")
SIMPLE_TIME_CONTROL = re.compile(r"(\d+)(?:\+(\d+))?")


def review_of_pgn(pgn: str) -> dict | None:
    """Turns a PGN game into the moves of a review.

    Args:
        pgn (str): One PGN game.

    Returns:
        dict | None: `start_fen` and `moves` (each with ply, SAN, UCI, FEN, its annotations and
            variations), or None if the PGN cannot be read.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None or game.errors:
        return None
    start = game.board()
    clocks = _Clocks(game.headers.get("TimeControl", ""))
    return {"start_fen": start.fen(), "moves": _line(game, start, clocks)}


def _line(parent: chess.pgn.GameNode, board: chess.Board, clocks: "_Clocks | None") -> list[dict]:
    """The line that continues from `parent`, with the variations that branch off each move.

    Args:
        parent (chess.pgn.GameNode): The node the line starts after.
        board (chess.Board): The position at `parent`; it is played forward.
        clocks (_Clocks | None): The clocks of the main line, or None inside a variation.

    Returns:
        list[dict]: The moves of the line.
    """
    moves = []
    node = parent
    while node.variations:
        main = node.variations[0]
        ply = board.ply() + 1
        san = board.san(main.move)
        alternatives = [_line_from(side, board.copy(stack=False)) for side in node.variations[1:]]
        board.push(main.move)
        move = {"ply": ply, "san": san, "uci": main.move.uci(), "fen": board.fen()}
        move.update(_annotations(main, clocks))
        if alternatives:
            move["variations"] = alternatives
        moves.append(move)
        node = main
    return moves


def _line_from(first: chess.pgn.ChildNode, board: chess.Board) -> list[dict]:
    """A side variation: its first move, then the line that continues from it.

    Args:
        first (chess.pgn.ChildNode): The variation's first move.
        board (chess.Board): The position before it; it is played forward.

    Returns:
        list[dict]: The moves of the variation.
    """
    ply = board.ply() + 1
    san = board.san(first.move)
    board.push(first.move)
    move = {"ply": ply, "san": san, "uci": first.move.uci(), "fen": board.fen()}
    move.update(_annotations(first, None))
    return [move, *_line(first, board, None)]


def _annotations(node: chess.pgn.ChildNode, clocks: "_Clocks | None") -> dict:
    """What the PGN says about a move: kind, symbols, evaluation, comment and clocks.

    Args:
        node (chess.pgn.ChildNode): The move.
        clocks (_Clocks | None): The main line's clocks, or None inside a variation.

    Returns:
        dict: Only the keys the PGN gives.
    """
    out: dict = {}
    kind = _kind(node)
    if kind:
        out["kind"] = kind
    symbols = [NAG_SYMBOLS[nag] for nag in sorted(node.nags) if nag in NAG_SYMBOLS]
    if symbols:
        out["symbol"] = " ".join(symbols)
    score = node.eval()
    if score is not None:
        white = score.white()
        out["eval"] = {"cp": white.score(), "mate": white.mate()}
    text = " ".join(COMMAND.sub(" ", node.comment).split())
    if text:
        out["comment"] = text
    if clocks is not None:
        out.update(clocks.after(node))
    return out


def _kind(node: chess.pgn.ChildNode) -> str | None:
    """The site's classification of a move: Chess.com's `[%c_effect]` type, else the NAG.

    Args:
        node (chess.pgn.ChildNode): The move.

    Returns:
        str | None: An icon kind such as `blunder`, or None.
    """
    for name in EFFECT_TYPE.findall(node.comment):
        if name.lower() in EFFECT_KINDS:
            return EFFECT_KINDS[name.lower()]
    for nag in sorted(node.nags):
        if nag in NAG_KINDS:
            return NAG_KINDS[nag]
    return None


class _Clocks:
    """The clock after each mainline move and the time the move took.

    The time comes from Chess.com's `[%timestamp]` (tenths of a second) when present; otherwise
    from the two clocks of the same side and the increment, which only a simple `base+increment`
    time control gives.

    Attributes:
        increment_ms (int | None): The increment, or None if the time control is not simple.
        last_ms (dict[chess.Color, int | None]): Each side's last clock.
    """

    def __init__(self, time_control: str) -> None:
        """Creates the clocks for a game.

        Args:
            time_control (str): The PGN `TimeControl` tag, such as `600+5`.
        """
        match = SIMPLE_TIME_CONTROL.fullmatch(time_control.strip())
        self.increment_ms = int(match.group(2) or 0) * 1000 if match else None
        base_ms = int(match.group(1)) * 1000 if match else None
        self.last_ms: dict[chess.Color, int | None] = {chess.WHITE: base_ms, chess.BLACK: base_ms}

    def after(self, node: chess.pgn.ChildNode) -> dict:
        """The clock after a move and the time it took, as far as the PGN tells.

        Args:
            node (chess.pgn.ChildNode): The move, in main-line order.

        Returns:
            dict: `clock_ms` and `spent_ms`, each only when known.
        """
        out: dict = {}
        side = not node.turn()  # the side that just moved
        seconds = node.clock()
        clock_ms = round(seconds * 1000) if seconds is not None else None
        if clock_ms is not None:
            out["clock_ms"] = clock_ms
        stamp = TIMESTAMP.search(node.comment)
        if stamp:
            out["spent_ms"] = int(stamp.group(1)) * 100
        elif clock_ms is not None and self.increment_ms is not None:
            last = self.last_ms[side]
            if last is not None and last + self.increment_ms >= clock_ms:
                out["spent_ms"] = last + self.increment_ms - clock_ms
        self.last_ms[side] = clock_ms
        return out


def pgn_of_line(variant: Variant) -> str:
    """A book line as a PGN game, ready to export.

    Args:
        variant (Variant): The line.

    Returns:
        str: The PGN, with `ECO` and `Opening` when the line has them.

    Raises:
        ValueError: The line's moves are not valid PGN.
    """
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
