"""Fetch a player's public games from Chess.com or Lichess as PGN text.

The text goes through the same import as a pasted PGN, so nothing here validates games.
This is the only part of the app that goes to the internet, and only when the user asks.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app import __version__

Site = Literal["lichess", "chesscom"]
FetchUrl = Callable[[str, str], bytes]
"""Takes a URL and the Accept header, returns the body or raises RemoteError."""

MAX_GAMES = 1000
USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,29}")
USER_AGENT = f"chess-trainer/{__version__} (+https://github.com/nielsencampos/chess-trainer)"
# Lichess perf types the app can import: every standard speed, and Chess960.
LICHESS_PERFS = "ultraBullet,bullet,blitz,rapid,classical,correspondence,chess960"
CHESSCOM_RULES = {"chess", "chess960"}
TIMEOUT_S = 120


class RemoteError(Exception):
    """A fetch that failed, with a code the UI translates.

    Attributes:
        code (str): `bad_username`, `user_not_found`, `rate_limited`, `unreachable` or
            `bad_response`.
    """

    def __init__(self, code: str) -> None:
        """Creates the error.

        Args:
            code (str): The reason's code.
        """
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Fetched:
    """The games fetched from a site.

    Attributes:
        pgn (str): The games as PGN text, oldest first.
        games (int): How many games it holds.
        truncated (bool): Whether the period had more than `MAX_GAMES` games.
    """

    pgn: str
    games: int
    truncated: bool


def fetch_url(url: str, accept: str) -> bytes:
    """Fetches a URL from the internet.

    Args:
        url (str): The URL.
        accept (str): The `Accept` header.

    Returns:
        bytes: The response body.

    Raises:
        RemoteError: `user_not_found` on 404, `rate_limited` on 429, `unreachable` otherwise.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise RemoteError("user_not_found") from error
        if error.code == 429:
            raise RemoteError("rate_limited") from error
        raise RemoteError("unreachable") from error
    except OSError as error:  # URLError and timeouts included
        raise RemoteError("unreachable") from error


def first_month(months: int, now: datetime) -> datetime:
    """Midnight UTC of the first day of the oldest month in the period (this month counts).

    Args:
        months (int): The period, in months.
        now (datetime): The current time.

    Returns:
        datetime: The start of the period.
    """
    index = now.year * 12 + now.month - 1 - (months - 1)
    return datetime(index // 12, index % 12 + 1, 1, tzinfo=UTC)


def fetch_games(
    site: Site, username: str, months: int, fetch: FetchUrl, now: datetime | None = None
) -> Fetched:
    """Fetches a player's public games of the last months, standard and Chess960.

    Args:
        site (Site): `lichess` or `chesscom`.
        username (str): The player's username.
        months (int): The period, in months, this month included.
        fetch (FetchUrl): How to fetch a URL; tests pass a fake.
        now (datetime | None): The current time; now when None.

    Returns:
        Fetched: The newest games of the period, at most `MAX_GAMES`.

    Raises:
        RemoteError: The username is malformed, or a fetch failed.
    """
    if not USERNAME.fullmatch(username):
        raise RemoteError("bad_username")
    since = first_month(months, now or datetime.now(UTC))
    if site == "lichess":
        return _lichess(username, since, fetch)
    return _chesscom(username, since, fetch)


def _lichess(username: str, since: datetime, fetch: FetchUrl) -> Fetched:
    """Fetches a player's games from the Lichess API, with clocks, analysis and opening.

    Args:
        username (str): The player's username.
        since (datetime): The start of the period.
        fetch (FetchUrl): How to fetch a URL.

    Returns:
        Fetched: The games.
    """
    query = urllib.parse.urlencode(
        {
            "since": int(since.timestamp() * 1000),
            "max": MAX_GAMES + 1,  # one more than kept tells that the period had more
            "perfType": LICHESS_PERFS,
            "clocks": "true",
            "evals": "true",
            "opening": "true",
            "literate": "true",
        }
    )
    url = f"https://lichess.org/api/games/user/{username}?{query}"
    text = fetch(url, "application/x-chess-pgn").decode("utf-8")
    games = re.split(r"\n\n(?=\[Event )", text.strip()) if text.strip() else []
    kept = games[:MAX_GAMES]
    return Fetched("\n\n".join(kept), len(kept), len(games) > MAX_GAMES)


def _chesscom(username: str, since: datetime, fetch: FetchUrl) -> Fetched:
    """Fetches a player's games from the Chess.com public API, one monthly archive at a time.

    Args:
        username (str): The player's username.
        since (datetime): The start of the period.
        fetch (FetchUrl): How to fetch a URL.

    Returns:
        Fetched: The newest games, oldest first.
    """
    base = f"https://api.chess.com/pub/player/{username.lower()}/games"
    archives = _json(fetch(f"{base}/archives", "application/json")).get("archives", [])
    oldest = f"{since.year:04d}/{since.month:02d}"
    wanted = sorted((url for url in archives if url[-7:] >= oldest), reverse=True)

    pgns: list[str] = []
    truncated = False
    for url in wanted:  # newest month first, one request at a time as the API asks
        month = _json(fetch(url, "application/json")).get("games", [])
        for game in sorted(month, key=lambda g: g.get("end_time", 0), reverse=True):
            if game.get("rules") not in CHESSCOM_RULES or not game.get("pgn"):
                continue
            if len(pgns) == MAX_GAMES:
                truncated = True
                break
            pgns.append(game["pgn"].strip())
        if truncated:
            break
    pgns.reverse()  # back to oldest first
    return Fetched("\n\n".join(pgns), len(pgns), truncated)


def _json(body: bytes) -> dict:
    """Parses a JSON object from a response.

    Args:
        body (bytes): The response body.

    Returns:
        dict: The object.

    Raises:
        RemoteError: `bad_response` if the body is not a JSON object.
    """
    try:
        data = json.loads(body)
    except ValueError as error:
        raise RemoteError("bad_response") from error
    if not isinstance(data, dict):
        raise RemoteError("bad_response")
    return data
