"""web/js/rules.js against python-chess, the rules the server uses.

A disagreement would show as a move the board offers and the server refuses, or the other way
around.
"""

import random

import chess
from playwright.sync_api import Page

RULES_URL = "/js/rules.js"


def run_rules(page: Page, script: str, argument: object) -> object:
    """Runs a function body in the browser, with `Rules` and `arg` in scope.

    Args:
        page (Page): The page.
        script (str): The body of an async function that returns a value.
        argument (object): The value of `arg`.

    Returns:
        object: What the script returns.
    """
    page.goto("/")
    return page.evaluate(
        f"""async (arg) => {{
            const {{ Rules }} = await import("{RULES_URL}");
            {script}
        }}""",
        argument,
    )


def snapshot(board: chess.Board) -> dict:
    """What the browser's rules should say about a position, by python-chess.

    Args:
        board (chess.Board): The position.

    Returns:
        dict: The FEN without counters, the legal moves, the checked king's square and whether the
            game is over.
    """
    moves: dict[str, dict] = {}
    for move in board.legal_moves:
        target = chess.square_name(move.to_square)
        key = f"{chess.square_name(move.from_square)}{target}"
        moves[key] = {
            "capture": board.is_capture(move),
            "promotion": move.promotion is not None,
        }
    return {
        "fen": " ".join(board.fen().split(" ")[:4]),
        "moves": moves,
        "check": chess.square_name(board.king(board.turn)) if board.is_check() else None,
        "over": board.is_repetition(3) or board.is_fifty_moves() or board.is_game_over(),
    }


def random_game(rng: random.Random, plies: int = 120) -> tuple[list[dict], list[dict]]:
    """Moves of a random game, favoring castling, and the expected state before each one.

    Args:
        rng (random.Random): The random source.
        plies (int): The most plies to play.

    Returns:
        tuple[list[dict], list[dict]]: The moves, and the snapshot before each move.
    """
    board = chess.Board()
    moves, states = [], []
    while len(moves) < plies:
        states.append(snapshot(board))
        legal = list(board.legal_moves)
        if not legal or states[-1]["over"]:
            break
        castles = [move for move in legal if board.is_castling(move)]
        move = rng.choice(castles) if castles else rng.choice(legal)
        uci = move.uci()
        moves.append(
            {
                "from": uci[:2],
                "to": uci[2:4],
                "promotion": uci[4:] or None,
                "san": board.san(move),
                "capture": board.is_capture(move),
                "castle": board.is_castling(move),
            }
        )
        board.push(move)
    return moves, states


REPLAY = """
    const squares = [];
    for (const file of "abcdefgh") for (const rank of "12345678") squares.push(file + rank);
    const state = (rules) => {
        const moves = {};
        for (const from of squares) {
            const piece = rules.pieceAt(from);
            if (!piece || piece.color !== rules.fen().split(" ")[1]) continue;
            for (const m of rules.movesFrom(from)) {
                moves[from + m.to] = { capture: m.capture, promotion: m.promotion };
            }
        }
        return {
            fen: rules.fen().split(" ").slice(0, 4).join(" "),
            moves,
            check: rules.checkSquare(),
            over: rules.isGameOver(),
        };
    };
    const rules = new Rules();
    const states = [];
    const played = [];
    for (const m of arg.moves) {
        states.push(state(rules));
        const move = arg.bySan
            ? rules.moveSan(m.san)
            : rules.move(m.from, m.to, m.promotion ?? undefined);
        played.push(move);
    }
    if (arg.states > arg.moves.length) states.push(state(rules));
    return { states, played };
"""


def test_rules_agree_with_python_chess(page: Page):
    """Rules agree with python-chess.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    rng = random.Random(960)
    castles = captures = promotions = 0
    for game in range(12):
        moves, expected = random_game(rng)
        result = run_rules(
            page,
            REPLAY,
            {"moves": moves, "bySan": game % 2 == 1, "states": len(expected)},
        )
        assert result["states"] == expected
        for move, played in zip(moves, result["played"], strict=True):
            assert played == {
                "san": move["san"],
                "uci": move["from"] + move["to"] + (move["promotion"] or ""),
                "capture": move["capture"],
                "castle": move["castle"],
            }
            castles += move["castle"]
            captures += move["capture"]
            promotions += move["promotion"] is not None
    # The games must really have exercised the special moves.
    assert castles > 0
    assert captures > 0
    assert promotions > 0


def test_castling_is_the_kings_two_square_move(page: Page):
    """Castling is the king's two-square move.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    result = run_rules(
        page,
        """
        const rules = new Rules();
        for (const san of ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]) rules.moveSan(san);
        const targets = rules.movesFrom("e1").map((m) => m.to);
        return { targets, rook: rules.move("e1", "h1"), king: rules.move("e1", "g1") };
        """,
        None,
    )
    assert "g1" in result["targets"]
    assert "h1" not in result["targets"]
    assert result["rook"] is None
    assert result["king"] == {"san": "O-O", "uci": "e1g1", "capture": False, "castle": True}


def test_en_passant_is_a_capture(page: Page):
    """En passant is a capture.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    result = run_rules(
        page,
        """
        const rules = new Rules();
        for (const san of ["e4", "a6", "e5", "d5"]) rules.moveSan(san);
        const target = rules.movesFrom("e5").find((m) => m.to === "d6");
        return { target, played: rules.move("e5", "d6") };
        """,
        None,
    )
    assert result["target"] == {"to": "d6", "capture": True, "promotion": False}
    assert result["played"] == {"san": "exd6", "uci": "e5d6", "capture": True, "castle": False}


def test_illegal_moves_are_refused_and_leave_the_position_alone(page: Page):
    """Illegal moves are refused and leave the position alone.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    result = run_rules(
        page,
        """
        const rules = new Rules();
        const before = rules.fen();
        return { played: rules.move("e2", "e5"), same: rules.fen() === before };
        """,
        None,
    )
    assert result == {"played": None, "same": True}


def test_threefold_repetition_ends_the_game_like_on_the_server(page: Page):
    """Threefold repetition ends the game like on the server.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    shuffle = ["Nf3", "Nf6", "Ng1", "Ng8"]
    board = chess.Board()
    for san in shuffle * 2:
        board.push_san(san)
    assert board.is_repetition(3)
    result = run_rules(
        page,
        """
        const rules = new Rules();
        const over = [];
        for (const san of arg) { rules.moveSan(san); over.push(rules.isGameOver()); }
        return over;
        """,
        shuffle * 2,
    )
    assert result == [False] * 7 + [True]


def castling_in_chess960(page: Page, fen: str, king: str, target: str) -> dict:
    """Asks the browser's rules for a king's targets and plays a castling move.

    Args:
        page (Page): The page.
        fen (str): A Chess960 position.
        king (str): The king's square.
        target (str): The square clicked.

    Returns:
        dict: The king's `targets`, whether it was `played`, and the `fen` after.
    """
    return run_rules(
        page,
        """
        const rules = new Rules(arg.fen);
        const targets = rules.movesFrom(arg.king).map((m) => m.to);
        return { targets, played: rules.move(arg.king, arg.target), fen: rules.fen() };
        """,
        {"fen": fen, "king": king, "target": target},
    )


def test_chess960_castles_on_a_square_between_or_on_the_rook(page: Page):
    """Chess960 castles on a square between or on the rook.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    fen = "4k3/8/8/8/8/8/8/1K5R w K - 0 1"
    between = castling_in_chess960(page, fen, "b1", "e1")
    # c1 is also a normal king move, so it stays one, and a1 and the second rank are normal too.
    assert set(between["targets"]) == {"a1", "c1", "a2", "b2", "c2", "d1", "e1", "f1", "g1", "h1"}
    assert between["played"] == {"san": "O-O", "uci": "b1h1", "capture": False, "castle": True}
    assert between["fen"].startswith("4k3/8/8/8/8/8/8/5RK1 b")
    on_rook = castling_in_chess960(page, fen, "b1", "h1")
    assert on_rook["played"]["uci"] == "b1h1"
    normal = castling_in_chess960(page, fen, "b1", "c1")
    assert normal["played"] == {"san": "Kc1", "uci": "b1c1", "capture": False, "castle": False}


def test_chess960_castling_with_nothing_between_uses_the_rook(page: Page):
    """Chess960 castling with nothing between uses the rook.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    # The king is already on its castled square, so only the rook can say "castle".
    result = castling_in_chess960(page, "4k3/8/8/8/8/8/8/6KR w K - 0 1", "g1", "h1")
    assert result["played"] == {"san": "O-O", "uci": "g1h1", "capture": False, "castle": True}
    assert result["fen"].startswith("4k3/8/8/8/8/8/8/5RK1 b")


def test_chess960_rules_agree_with_python_chess_on_a_random_game(page: Page):
    """Chess960 rules agree with python-chess on a random game.

    Args:
        page (Page): A fresh page at 1280x720; an uncaught page error fails the test.
    """
    rng = random.Random(96)
    for _ in range(6):
        position = rng.randrange(960)
        board = chess.Board.from_chess960_pos(position)
        fen = board.fen()
        moves = []
        for _ply in range(60):
            legal = list(board.legal_moves)
            if not legal or board.is_game_over():
                break
            castles = [move for move in legal if board.is_castling(move)]
            move = rng.choice(castles) if castles else rng.choice(legal)
            moves.append({"uci": move.uci(), "san": board.san(move)})
            board.push(move)
        result = run_rules(
            page,
            """
            const rules = new Rules(arg.fen);
            const played = [];
            for (const m of arg.moves) {
                const promotion = m.uci[4];
                played.push(rules.move(m.uci.slice(0, 2), m.uci.slice(2, 4), promotion));
            }
            return { played: played.map((m) => m && [m.uci, m.san]), fen: rules.fen() };
            """,
            {"fen": fen, "moves": moves},
        )
        assert result["played"] == [[m["uci"], m["san"]] for m in moves]
        assert result["fen"].split(" ")[:4] == board.fen().split(" ")[:4]
