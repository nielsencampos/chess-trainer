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
class Period:
    """Time added to a player's clock when they complete this many moves."""

    after_moves: int
    add_ms: int


@dataclass(frozen=True)
class TimeControl:
    base_ms: int
    increment_ms: int = 0
    periods: tuple[Period, ...] = ()
    delay_ms: int = 0
    # "bronstein": time used is given back, up to the delay. "us": the clock waits for the delay.
    delay_kind: str | None = None

    @property
    def per_move_ms(self) -> int:
        return self.increment_ms + self.delay_ms


def _control(
    *minutes: int, increment_s: int = 0, delay_s: int = 0, delay_kind: str | None = None
) -> TimeControl:
    """Minutes of the first period, then of later ones, added on moves 40 and 60."""
    after_moves = (40, 60)
    return TimeControl(
        base_ms=minutes[0] * 60_000,
        increment_ms=increment_s * 1000,
        periods=tuple(
            Period(after, extra * 60_000)
            for after, extra in zip(after_moves, minutes[1:], strict=False)
        ),
        delay_ms=delay_s * 1000,
        delay_kind=delay_kind,
    )


# By category. Bullet is ours, and the rest are the presets of a DGT 3000 clock. Keys: minutes per
# period, or seconds with an s, then i (increment), d (Bronstein delay) or u (US delay) in seconds.
TIME_CONTROL_GROUPS: dict[str, dict[str, TimeControl]] = {
    "bullet": {
        "30s": TimeControl(base_ms=30_000),
        "1": _control(1),
        "2": _control(2),
    },
    "blitz": {
        "5": _control(5),
        "10": _control(10),
        "3i2": _control(3, increment_s=2),
        "5u2": _control(5, delay_s=2, delay_kind="us"),
    },
    "rapid": {
        "25": _control(25),
        "25i10": _control(25, increment_s=10),
        "25d10": _control(25, delay_s=10, delay_kind="bronstein"),
        "25u5": _control(25, delay_s=5, delay_kind="us"),
    },
    "classical": {
        "60": _control(60),
        "120": _control(120),
        "120+30": _control(120, 30),
        "120+60": _control(120, 60),
        "120+60+30": _control(120, 60, 30),
        "120+60+60": _control(120, 60, 60),
        "90i30": _control(90, increment_s=30),
        "90+30i30": _control(90, 30, increment_s=30),
        "100+50+15i30": _control(100, 50, 15, increment_s=30),
        "115d5": _control(115, delay_s=5, delay_kind="bronstein"),
        "120+15d30": _control(120, 15, delay_s=30, delay_kind="bronstein"),
        "120+60+15d30": _control(120, 60, 15, delay_s=30, delay_kind="bronstein"),
        "115+60u5": _control(115, 60, delay_s=5, delay_kind="us"),
    },
}
NO_CLOCK = "none"
DEFAULT_TIME_CONTROL = "25i10"
# Writing moves on paper is for long games and for free play, not for on-screen training.
SCORESHEET_GROUPS = {"classical"}

TIME_CONTROLS: dict[str, TimeControl | None] = {
    NO_CLOCK: None,
    **{key: control for group in TIME_CONTROL_GROUPS.values() for key, control in group.items()},
}


def clock_after_move(control: TimeControl, remaining_ms: int, used_ms: int, moves_made: int) -> int:
    """A player's clock after a move, by the same rules as the clock in the browser."""
    charged = max(0, used_ms - control.delay_ms) if control.delay_kind == "us" else used_ms
    after = max(0, remaining_ms - charged) + control.increment_ms
    if control.delay_kind == "bronstein":
        after += min(used_ms, control.delay_ms)
    for period in control.periods:
        if period.after_moves == moves_made:
            after += period.add_ms
    return after


def engine_budget_s(time_control: TimeControl | None, remaining_ms: int | None) -> float | None:
    """The most one search may take on the bot's clock. None means no limit."""
    if time_control is None or remaining_ms is None:
        return None
    budget_ms = remaining_ms / ENGINE_MOVES_LEFT + time_control.per_move_ms * INCREMENT_SHARE
    return max(MIN_ENGINE_TIME_S, min(budget_ms, remaining_ms / 2) / 1000)


def human_delay_ms(
    time_control: TimeControl | None, remaining_ms: int | None, in_book: bool, rng: random.Random
) -> int:
    """How long the bot appears to think. In book it answers much faster.

    At 90 + 30 min with 30 s this gives about 110-180 s out of book and 9-27 s in book at the start.
    Never more than half of the remaining time, so the bot does not flag itself by pacing.
    """
    if time_control is None or remaining_ms is None:
        low, high = NO_CLOCK_BOOK_RANGE_MS if in_book else NO_CLOCK_RANGE_MS
        return rng.randint(low, high)
    target = remaining_ms / EXPECTED_MOVES_LEFT + time_control.per_move_ms * INCREMENT_SHARE
    delay = (
        target * BOOK_SHARE * rng.uniform(0.5, 1.5) if in_book else target * rng.uniform(0.75, 1.2)
    )
    return int(max(MIN_DELAY_MS, min(delay, remaining_ms / 2)))
