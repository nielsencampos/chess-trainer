"""Bot deviation (brief §6): the die, the choice of move, take-backs, saving and the API."""

import asyncio
import random

import chess
import pytest

from app.book.models import Book, BookMoveRow, Variant, index_moves
from app.db.connection import apply_migrations, open_database
from app.engine.levels import Level
from app.game.service import GameService
from app.game.session import BotDeviationSetup, GameSession, Selection
from app.game.store import GameStore, restore_session
from tests.conftest import FakeEngine

MAIN = "e4 e5 Nf3 Nc6 Bb5 a6 Ba4"
SIDELINE = "e4 e5 Nf3 Nf6"
SHORT = "e4 e5 Nf3"


class AlwaysHit(random.Random):
    """A random source whose die always hits, so a deviation happens on the first roll."""

    def randrange(self, *args, **kwargs) -> int:
        """Always the lowest value.

        Args:
            *args: Ignored.
            **kwargs: Ignored.

        Returns:
            int: 0.
        """
        return 0


def line(variant_id: str, sans: str) -> Variant:
    """A test line from space-separated SAN moves.

    Args:
        variant_id (str): The line id.
        sans (str): The moves.

    Returns:
        Variant: The line.
    """
    board = chess.Board()
    rows = []
    for ply, san in enumerate(sans.split(), 1):
        move = board.parse_san(san)
        rows.append(BookMoveRow(board.epd(), ply, move.uci(), san))
        board.push(move)
    moves, positions = index_moves(rows, board.epd())
    return Variant(
        variant_id,
        "test",
        {"en-US": variant_id},
        None,
        None,
        "test",
        sans,
        moves,
        positions,
        board.epd(),
    )


def service(engine, tmp_path, *variants: Variant, max_loss_cp: int = 100) -> GameService:
    """A game service over a book of test lines, whose die always hits.

    Args:
        engine (FakeEngine): The fake engine.
        tmp_path (Path): A folder for the database.
        *variants (Variant): The book's lines.
        max_loss_cp (int): The most an engine deviation may lose.

    Returns:
        GameService: The service.
    """
    database = open_database(tmp_path / "games.duckdb")
    apply_migrations(database)
    book = Book({}, {variant.variant_id: variant for variant in variants})
    level = Level("club", "1320", {}, chess.engine.Limit(time=0.1))
    return GameService(
        book, engine, {"club": level}, GameStore(database), AlwaysHit(), {}, max_loss_cp
    )


def start(games: GameService, variant_ids: list[str], from_move: int = 2) -> GameSession:
    """Starts a game as White with the bot allowed to deviate.

    Args:
        games (GameService): The service.
        variant_ids (list[str]): The selected lines.
        from_move (int): The first move the bot rolls on.

    Returns:
        GameSession: The game.
    """
    session, _ = asyncio.run(
        games.create_game(
            "white",
            variant_ids,
            "club",
            "instant",
            "none",
            bot_deviation=BotDeviationSetup(from_move, 70),
        )
    )
    return session


def play(games: GameService, session: GameSession, san: str):
    """Plays the user's move and the bot's reply.

    Args:
        games (GameService): The service.
        session (GameSession): The game.
        san (str): The user's move.

    Returns:
        BotReply | None: The bot's reply.
    """
    uci = session.board.parse_san(san).uci()
    _, _, _, reply = asyncio.run(games.user_move(session.game_id, uci, None, None, None))
    return reply


class SlowEngine(FakeEngine):
    """The fake engine, with a search that takes a moment, so requests can overlap it."""

    async def play(self, board, level, max_time_s=None):
        """Waits, then plays as the fake engine.

        Args:
            board (chess.Board): The position.
            level (Level): Ignored.
            max_time_s (float | None): Recorded.

        Returns:
            chess.Move: The move.
        """
        await asyncio.sleep(0.05)
        return await super().play(board, level, max_time_s)


def test_a_resume_during_the_bot_search_does_not_play_twice(tmp_path):
    """A reload while the bot searches waits for its move instead of playing another one.

    Args:
        tmp_path (Path): A folder for the database.
    """
    games = service(SlowEngine(), tmp_path, line("short", "e4"))
    session = start(games, ["short"])

    async def move_and_reload():
        task = asyncio.create_task(games.user_move(session.game_id, "e2e4", None, None, None))
        await asyncio.sleep(0.01)
        await games.resume_active()
        return await task

    _, _, _, reply = asyncio.run(move_and_reload())
    assert reply is not None
    assert [record.by for record in session.moves] == ["user", "bot"]
    assert session.is_user_turn


def test_a_take_back_during_the_bot_search_drops_its_move(tmp_path):
    """A take-back while the bot searches undoes the user's move, and the search is dropped.

    Args:
        tmp_path (Path): A folder for the database.
    """
    games = service(SlowEngine(), tmp_path, line("short", "e4"))
    session = start(games, ["short"])

    async def move_and_take_back():
        task = asyncio.create_task(games.user_move(session.game_id, "e2e4", None, None, None))
        await asyncio.sleep(0.01)
        games.take_back(session.game_id, 1, None, None)
        return await task

    _, _, _, reply = asyncio.run(move_and_take_back())
    assert reply is None
    assert session.ply == 0
    assert session.is_user_turn


def test_a_take_back_and_another_move_during_the_bot_search_drop_its_move(tmp_path):
    """A take-back and a new move during the search bring the ply back: the old search is dropped.

    Args:
        tmp_path (Path): A folder for the database.
    """
    games = service(SlowEngine(), tmp_path, line("short", "e4"))
    session = start(games, ["short"])

    async def move_take_back_and_move():
        first = asyncio.create_task(games.user_move(session.game_id, "d2d4", None, None, None))
        await asyncio.sleep(0.01)  # the bot searches the position after 1.d4
        games.take_back(session.game_id, 1, None, None)
        second = asyncio.create_task(games.user_move(session.game_id, "e2e4", None, None, None))
        return (await first)[3], (await second)[3]

    first, second = asyncio.run(move_take_back_and_move())
    assert first is None
    assert second is not None
    assert [record.san for record in session.moves] == ["e4", second.record.san]


class SlowEvaluation(FakeEngine):
    """The fake engine, with an evaluation that takes a moment, as a bot deviation's search does."""

    async def evaluate(self, board, time_s, root_moves=None):
        """Waits, then evaluates as the fake engine.

        Args:
            board (chess.Board): The position.
            time_s (float): Ignored.
            root_moves (Sequence[chess.Move] | None): The moves to choose from, if given.

        Returns:
            The fake engine's evaluation.
        """
        await asyncio.sleep(0.05)
        return await super().evaluate(board, time_s, root_moves)


def test_a_take_back_during_a_bot_deviation_search_drops_its_move(tmp_path):
    """A take-back while the bot looks for a deviation undoes the move, and the search is dropped.

    Args:
        tmp_path (Path): A folder for the database.
    """
    games = service(SlowEvaluation(), tmp_path, line("main", MAIN))
    session = start(games, ["main"])
    assert play(games, session, "e4").record.san == "e5"  # move 1: no roll

    async def move_and_take_back():
        task = asyncio.create_task(games.user_move(session.game_id, "g1f3", None, None, None))
        await asyncio.sleep(0.01)  # move 2: the die hits, the bot evaluates its options
        games.take_back(session.game_id, 3, None, None)
        return await task

    _, _, _, reply = asyncio.run(move_and_take_back())
    assert reply is None
    assert [record.san for record in session.moves] == ["e4", "e5"]
    assert session.bot_deviation is None


def test_the_bot_rolls_only_from_its_move_and_never_before(engine, tmp_path):
    """Before the chosen move the bot follows its line; from it, a hit makes it deviate.

    Args:
        engine (FakeEngine): The fake engine.
        tmp_path (Path): A folder for the database.
    """
    games = service(engine, tmp_path, line("main", MAIN), line("side", SIDELINE))
    session = start(games, ["main"])
    assert play(games, session, "e4").record.san == "e5"  # move 1: no roll
    reply = play(games, session, "Nf3")  # move 2: the die hits
    assert reply.record.san == "Nf6"
    assert reply.record.source == "book"
    assert session.bot_deviation is not None
    assert session.bot_deviation.expected_san == ("Nc6",)
    assert session.in_theory is False
    assert session.deviations == []
    assert "{ Bot deviation: line expected Nc6 }" in session.pgn()


def test_the_die_does_not_roll_out_of_theory():
    """The die rolls only while the game is in theory."""
    game = GameSession(
        "g",
        Selection([line("main", MAIN)]),
        chess.BLACK,
        "none",
        None,
        "club",
        "instant",
        AlwaysHit(),
    )
    game.bot_deviation_setup = BotDeviationSetup(1, 70)
    assert game.rolls_for_deviation()
    game.in_theory = False
    assert not game.rolls_for_deviation()


def test_without_a_sideline_the_engine_deviates_within_the_limit(engine, tmp_path):
    """With no book sideline, the engine's best move outside the lines is played.

    Args:
        engine (FakeEngine): The fake engine, which scores by material.
        tmp_path (Path): A folder for the database.
    """
    games = service(engine, tmp_path, line("main", MAIN))
    session = start(games, ["main"])
    play(games, session, "e4")
    reply = play(games, session, "Nf3")
    assert reply.record.source == "engine"
    assert reply.record.san != "Nc6"
    assert session.bot_deviation is not None
    assert session.bot_deviation.played_san == reply.record.san


def test_an_engine_move_over_the_limit_is_refused(engine, tmp_path):
    """When no move is good enough, the bot plays its line and rolls again later.

    Args:
        engine (FakeEngine): The fake engine.
        tmp_path (Path): A folder for the database.
    """
    games = service(engine, tmp_path, line("main", MAIN), max_loss_cp=-1)
    session = start(games, ["main"])
    play(games, session, "e4")
    assert play(games, session, "Nf3").record.san == "Nc6"
    assert session.bot_deviation is None
    assert session.in_theory is True


def test_the_line_ending_stops_the_rolls(engine, tmp_path):
    """Once the drawn line has no move for the bot, the engine takes over without deviating.

    Args:
        engine (FakeEngine): The fake engine.
        tmp_path (Path): A folder for the database.
    """
    games = service(engine, tmp_path, line("short", SHORT), line("side", SIDELINE))
    session = start(games, ["short"])
    play(games, session, "e4")
    play(games, session, "Nf3")
    assert session.bot_deviation is None


def test_take_back_removes_the_deviation(engine, tmp_path):
    """Taking back the user's move also takes back the bot's deviation that answered it.

    Args:
        engine (FakeEngine): The fake engine.
        tmp_path (Path): A folder for the database.
    """
    games = service(engine, tmp_path, line("main", MAIN), line("side", SIDELINE))
    session = start(games, ["main"])
    play(games, session, "e4")
    play(games, session, "Nf3")
    session.take_back(3)
    assert session.bot_deviation is None
    assert session.in_theory is True


def test_a_resumed_game_keeps_the_setup_and_the_deviation(engine, tmp_path):
    """The setup and the bot's deviation are saved with the game and read back.

    Args:
        engine (FakeEngine): The fake engine.
        tmp_path (Path): A folder for the database.
    """
    main, side = line("main", MAIN), line("side", SIDELINE)
    games = service(engine, tmp_path, main, side)
    session = start(games, ["main"])
    play(games, session, "e4")
    play(games, session, "Nf3")
    row = games.store.active_row()
    restored = restore_session(row, games.book, {}, random.Random(1), games.store)
    assert restored.bot_deviation_setup == BotDeviationSetup(2, 70)
    assert restored.bot_deviation == session.bot_deviation


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"from_move": 3, "chance": 30}, 201),
        ({"from_move": 2, "chance": 30}, 422),
        ({"from_move": 3, "chance": 25}, 422),
    ],
)
def test_the_api_accepts_only_the_offered_choices(client, body, status):
    """The API takes the setup's choices only: moves 3 to 7 and 20 to 70% in steps of 10.

    Args:
        client (TestClient): The API with the fake engine.
        body (dict): The bot deviation setup sent.
        status (int): The expected HTTP status.
    """
    variant_id = client.get("/api/repertoires").json()["repertoires"][0]["variants"][0][
        "variant_id"
    ]
    response = client.post(
        "/api/games",
        json={
            "color": "white",
            "variant_ids": [variant_id],
            "level": "club",
            "pace": "instant",
            "time_control": "none",
            "bot_deviation": body,
        },
    )
    assert response.status_code == status
    if status == 201:
        assert response.json()["state"]["bot_deviation"] is None
