"""Bot response time. "Human" is decided by the backend, based on the clock (brief §9)."""

import random
from dataclasses import dataclass

MIN_DELAY_MS = 200
NO_CLOCK_RANGE_MS = (2000, 6000)
NO_CLOCK_BOOK_RANGE_MS = (500, 1500)
EXPECTED_MOVES_LEFT = 40
INCREMENT_SHARE = 0.5
BOOK_SHARE = 0.12


# The engine budget: the share of the clock one search may use, so it cannot flag itself.
ENGINE_MOVES_LEFT = 30
MIN_ENGINE_TIME_S = 0.01


@dataclass(frozen=True)
class TimeControl:
    base_ms: int
    increment_ms: int
    moves_to_bonus: int | None = None
    bonus_ms: int = 0


def _minutes(minutes: int, increment_s: int = 0) -> TimeControl:
    return TimeControl(minutes * 60_000, increment_s * 1000)


def _seconds(seconds: int, increment_s: int = 0) -> TimeControl:
    return TimeControl(seconds * 1000, increment_s * 1000)


def _classical(minutes: int, bonus_minutes: int, increment_s: int) -> TimeControl:
    """The bonus is added when a player completes move 40; the increment runs from move 1."""
    return TimeControl(minutes * 60_000, increment_s * 1000, 40, bonus_minutes * 60_000)


TIME_CONTROL_GROUPS: dict[str, dict[str, TimeControl]] = {
    "bullet": {
        "20s+1": _seconds(20, 1),
        "30s+0": _seconds(30),
        "1+0": _minutes(1),
        "1+1": _minutes(1, 1),
        "2+1": _minutes(2, 1),
    },
    "blitz": {
        "3+0": _minutes(3),
        "3+2": _minutes(3, 2),
        "5+0": _minutes(5),
        "5+3": _minutes(5, 3),
    },
    "rapid": {
        "10+0": _minutes(10),
        "10+5": _minutes(10, 5),
        "15+10": _minutes(15, 10),
        "20+0": _minutes(20),
        "30+0": _minutes(30),
        "60+0": _minutes(60),
    },
    "classical": {
        "90+30+30": _classical(90, 30, 30),
        "45+15+15": _classical(45, 15, 15),
    },
}
NO_CLOCK = "none"
DEFAULT_TIME_CONTROL = "10+5"
# Writing moves on paper is for long games and for free play, not for on-screen training.
SCORESHEET_GROUPS = {"classical"}

TIME_CONTROLS: dict[str, TimeControl | None] = {
    NO_CLOCK: None,
    **{key: control for group in TIME_CONTROL_GROUPS.values() for key, control in group.items()},
}


def engine_budget_s(time_control: TimeControl | None, remaining_ms: int | None) -> float | None:
    """The most one search may take on the bot's clock. None means no limit."""
    if time_control is None or remaining_ms is None:
        return None
    budget_ms = remaining_ms / ENGINE_MOVES_LEFT + time_control.increment_ms * INCREMENT_SHARE
    return max(MIN_ENGINE_TIME_S, min(budget_ms, remaining_ms / 2) / 1000)


def human_delay_ms(
    time_control: TimeControl | None, remaining_ms: int | None, in_book: bool, rng: random.Random
) -> int:
    """How long the bot appears to think. In book it answers much faster.

    At 90+30+30 this gives about 110-180 s out of book and 9-27 s in book at the start of a game.
    Never more than half of the remaining time, so the bot does not flag itself by pacing.
    """
    if time_control is None or remaining_ms is None:
        low, high = NO_CLOCK_BOOK_RANGE_MS if in_book else NO_CLOCK_RANGE_MS
        return rng.randint(low, high)
    target = remaining_ms / EXPECTED_MOVES_LEFT + time_control.increment_ms * INCREMENT_SHARE
    delay = (
        target * BOOK_SHARE * rng.uniform(0.5, 1.5) if in_book else target * rng.uniform(0.75, 1.2)
    )
    return int(max(MIN_DELAY_MS, min(delay, remaining_ms / 2)))
