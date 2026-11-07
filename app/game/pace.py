"""Bot response time. "Human" is decided by the backend, based on the clock (brief §9)."""

import random
from dataclasses import dataclass

MIN_DELAY_MS = 200
NO_CLOCK_RANGE_MS = (2000, 6000)
NO_CLOCK_BOOK_RANGE_MS = (500, 1500)
EXPECTED_MOVES_LEFT = 40
INCREMENT_SHARE = 0.5
BOOK_SHARE = 0.12


@dataclass(frozen=True)
class TimeControl:
    base_ms: int
    increment_ms: int


TIME_CONTROLS: dict[str, TimeControl | None] = {
    "3+2": TimeControl(3 * 60_000, 2_000),
    "10+5": TimeControl(10 * 60_000, 5_000),
    "15+10": TimeControl(15 * 60_000, 10_000),
    "45+30": TimeControl(45 * 60_000, 30_000),
    "none": None,
}


def human_delay_ms(
    time_control: TimeControl | None, remaining_ms: int | None, in_book: bool, rng: random.Random
) -> int:
    """How long the bot appears to think. In book it answers much faster.

    At 45+30 this gives about 60-100 s out of book and 5-15 s in book at the start of a game.
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
