"""Importing a player's games from Lichess and Chess.com, with the network replaced by a fake."""

import json
from datetime import UTC, datetime

import pytest

from app.game import remote
from app.game.remote import RemoteError, fetch_games, first_month


def game(white: str, moves: str, date: str = "2026.11.01", extra: str = "") -> str:
    """A minimal PGN game.

    Args:
        white (str): White's name, also used to find it.
        moves (str): The movetext.
        date (str): The PGN date.
        extra (str): More tag lines.

    Returns:
        str: The PGN.
    """
    return (
        f'[Event "Rated blitz game"]\n[White "{white}"]\n[Black "Opponent"]\n'
        f'[Date "{date}"]\n[Result "1-0"]\n{extra}\n{moves} 1-0\n'
    )


LICHESS_PGN = (
    game(
        "Ana",
        "1. e4 { [%eval 0.18] [%clk 0:05:00] } 1... e5 2. f4?! "
        "{ (0.22 → -0.34) Inaccuracy. Nf3 was best. } (2. Nf3 Nc6) 2... exf4",
    )
    + "\n\n"
    + game("Ana", "1. d4 d5 2. c4")
)


class FakeWeb:
    """Answers URLs from a table and records what was asked.

    Attributes:
        pages (dict[str, bytes | RemoteError]): URL prefix -> body, or the error to raise.
        asked (list[str]): The URLs asked, in order.
    """

    def __init__(self, pages: dict[str, bytes | RemoteError]) -> None:
        """Creates the fake.

        Args:
            pages (dict[str, bytes | RemoteError]): URL prefix -> body, or the error to raise.
        """
        self.pages = pages
        self.asked: list[str] = []

    def __call__(self, url: str, accept: str) -> bytes:
        """Answers a URL like `fetch_url`.

        Args:
            url (str): The URL.
            accept (str): The `Accept` header, ignored.

        Returns:
            bytes: The body of the first prefix that matches.

        Raises:
            RemoteError: The table says so, or `user_not_found` if nothing matches.
        """
        self.asked.append(url)
        for prefix, page in self.pages.items():
            if url.startswith(prefix):
                if isinstance(page, RemoteError):
                    raise page
                return page
        raise RemoteError("user_not_found")


def chesscom_month(*games: dict) -> bytes:
    """A Chess.com monthly archive.

    Args:
        *games (dict): The archive's games.

    Returns:
        bytes: The JSON body.
    """
    return json.dumps({"games": list(games)}).encode()


NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)


def test_first_month_counts_the_current_month_and_crosses_years():
    """First month counts the current month and crosses years."""
    assert first_month(1, NOW) == datetime(2026, 11, 1, tzinfo=UTC)
    assert first_month(12, NOW) == datetime(2025, 12, 1, tzinfo=UTC)
    assert first_month(3, datetime(2026, 1, 31, tzinfo=UTC)) == datetime(2025, 11, 1, tzinfo=UTC)


@pytest.mark.parametrize("name", ["", "a b", "x/../y", "a?b=c", "é", "-dash", "a" * 31])
def test_a_username_that_is_not_one_never_reaches_a_url(name):
    """A username that is not one never reaches a URL.

    Args:
        name (str): Something that is not a username.
    """
    web = FakeWeb({})
    with pytest.raises(RemoteError, match="bad_username"):
        fetch_games("lichess", name, 1, web, NOW)
    assert web.asked == []


def test_lichess_asks_for_the_period_clocks_and_analysis():
    """Lichess asks for the period clocks and analysis."""
    web = FakeWeb({"https://lichess.org/api/games/user/Ana?": LICHESS_PGN.encode()})
    fetched = fetch_games("lichess", "Ana", 3, web, NOW)
    assert (fetched.games, fetched.truncated) == (2, False)
    url = web.asked[0]
    since = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000)
    for part in (f"since={since}", "clocks=true", "evals=true", "literate=true", "chess960"):
        assert part in url


def test_lichess_keeps_at_most_the_limit(monkeypatch):
    """Lichess keeps at most the limit.

    Args:
        monkeypatch (pytest.MonkeyPatch): pytest's patcher.
    """
    monkeypatch.setattr(remote, "MAX_GAMES", 1)
    web = FakeWeb({"https://lichess.org/": LICHESS_PGN.encode()})
    fetched = fetch_games("lichess", "Ana", 1, web, NOW)
    assert (fetched.games, fetched.truncated) == (1, True)
    assert "1. d4" not in fetched.pgn


def test_chesscom_reads_only_the_months_of_the_period_and_skips_other_variants():
    """Chess.com reads only the months of the period and skips other variants."""
    base = "https://api.chess.com/pub/player/ana/games"
    archives = {"archives": [f"{base}/2026/08", f"{base}/2026/10", f"{base}/2026/11"]}
    web = FakeWeb(
        {
            f"{base}/archives": json.dumps(archives).encode(),
            f"{base}/2026/11": chesscom_month(
                {"rules": "chess", "end_time": 2, "pgn": game("Ana", "1. e4 e5")},
                {"rules": "crazyhouse", "end_time": 3, "pgn": game("Ana", "1. e4 e5 2. Nf3")},
            ),
            f"{base}/2026/10": chesscom_month(
                {"rules": "chess", "end_time": 1, "pgn": game("Ana", "1. c4 e5")}
            ),
        }
    )
    fetched = fetch_games("chesscom", "Ana", 2, web, NOW)
    assert (fetched.games, fetched.truncated) == (2, False)
    assert f"{base}/2026/08" not in web.asked
    assert fetched.pgn.index("1. c4") < fetched.pgn.index("1. e4")  # oldest first


def test_chesscom_stops_at_the_limit_keeping_the_newest(monkeypatch):
    """Chess.com stops at the limit keeping the newest.

    Args:
        monkeypatch (pytest.MonkeyPatch): pytest's patcher.
    """
    monkeypatch.setattr(remote, "MAX_GAMES", 1)
    base = "https://api.chess.com/pub/player/ana/games"
    web = FakeWeb(
        {
            f"{base}/archives": json.dumps(
                {"archives": [f"{base}/2026/10", f"{base}/2026/11"]}
            ).encode(),
            f"{base}/2026/11": chesscom_month(
                {"rules": "chess", "end_time": 5, "pgn": game("Ana", "1. e4 e5")}
            ),
            f"{base}/2026/10": chesscom_month(
                {"rules": "chess", "end_time": 1, "pgn": game("Ana", "1. c4 e5")}
            ),
        }
    )
    fetched = fetch_games("chesscom", "Ana", 2, web, NOW)
    assert (fetched.games, fetched.truncated) == (1, True)
    assert "1. e4" in fetched.pgn


def test_chesscom_garbage_is_a_bad_response():
    """Chess.com garbage is a bad response."""
    web = FakeWeb({"https://api.chess.com/": b"<html>"})
    with pytest.raises(RemoteError, match="bad_response"):
        fetch_games("chesscom", "ana", 1, web, NOW)


def remote_import(client, web, **body):
    """Calls the remote import with the network replaced.

    Args:
        client (TestClient): The API client.
        web (FakeWeb): The fake network.
        **body (object): The request's fields; one month by default.

    Returns:
        Response: The API's response.
    """
    client.app.state.fetch_url = web
    return client.post("/api/games/import/remote", json={"months": 1, **body})


def test_imported_games_keep_evals_comments_and_side_lines(client):
    """Imported games keep evaluations comments and side lines.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    web = FakeWeb({"https://lichess.org/": LICHESS_PGN.encode()})
    response = remote_import(client, web, site="lichess", username="Ana")
    assert response.json() == {
        "imported": 2,
        "duplicates": 0,
        "updated": 0,
        "errors": [],
        "fetched": 2,
        "truncated": False,
    }
    again = remote_import(client, web, site="lichess", username="Ana").json()
    assert (again["imported"], again["duplicates"]) == (0, 2)

    games = client.get("/api/games").json()["games"]
    pgn = client.post("/api/games/export", json={"game_ids": [g["game_id"] for g in games]}).text
    assert "[%eval 0.18]" in pgn and "Inaccuracy. Nf3 was best." in pgn
    assert "( 2. Nf3 Nc6 )" in pgn


def test_a_bad_game_from_the_site_is_listed_like_a_pasted_one(client):
    """A bad game from the site is listed like a pasted one.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    bad = game("Ana", "1. e4 e4")
    web = FakeWeb({"https://lichess.org/": bad.encode()})
    report = remote_import(client, web, site="lichess", username="Ana").json()
    assert report["imported"] == 0
    assert [e["code"] for e in report["errors"]] == ["invalid_moves"]


def test_no_games_in_the_period_is_not_an_error(client):
    """No games in the period is not an error.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    web = FakeWeb({"https://lichess.org/": b""})
    report = remote_import(client, web, site="lichess", username="Ana").json()
    assert report == {
        "imported": 0,
        "duplicates": 0,
        "updated": 0,
        "errors": [],
        "fetched": 0,
        "truncated": False,
    }


@pytest.mark.parametrize(
    ("error", "status"),
    [("user_not_found", 404), ("rate_limited", 429), ("unreachable", 502), ("bad_response", 502)],
)
def test_site_failures_map_to_status_codes(client, error, status):
    """Site failures map to status codes.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
        error (str): The site failure's code.
        status (int): The HTTP status it maps to.
    """
    web = FakeWeb({"https://lichess.org/": RemoteError(error)})
    response = remote_import(client, web, site="lichess", username="Ana")
    assert (response.status_code, response.json()["detail"]) == (status, error)


def test_the_request_is_checked(client):
    """The request is checked.

    Args:
        client (TestClient): The API on a fresh copy of the database, with the fake engine.
    """
    web = FakeWeb({})
    assert remote_import(client, web, site="lichess", username="a b").status_code == 422
    assert remote_import(client, web, site="other", username="Ana").status_code == 422
    assert remote_import(client, web, site="lichess", username="Ana", months=13).status_code == 422
    assert web.asked == []
