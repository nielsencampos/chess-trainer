import random

import chess.engine

from app.engine.levels import Level
from app.engine.process import limit_for
from app.game.pace import TIME_CONTROLS, engine_budget_s, human_delay_ms

LONG = TIME_CONTROLS["90+30i30"]
BLITZ = TIME_CONTROLS["3i2"]


def samples(time_control, remaining, in_book):
    rng = random.Random(1)
    return [human_delay_ms(time_control, remaining, in_book, rng) for _ in range(500)]


def test_classical_out_of_book_is_about_two_to_three_minutes():
    delays = samples(LONG, LONG.base_ms, in_book=False)
    assert min(delays) >= 110_000 and max(delays) <= 180_000


def test_classical_in_book_is_much_faster():
    delays = samples(LONG, LONG.base_ms, in_book=True)
    assert min(delays) >= 9_000 and max(delays) <= 27_000


def test_bullet_bot_does_not_flag_itself_by_pacing():
    control = TIME_CONTROLS["30s"]
    assert max(samples(control, control.base_ms, in_book=False)) < 1_000
    assert max(samples(control, 500, in_book=False)) <= 250


def test_blitz_is_much_faster():
    assert max(samples(BLITZ, BLITZ.base_ms, in_book=False)) < 8_000


def test_no_clock_uses_fixed_ranges():
    assert all(2000 <= delay <= 6000 for delay in samples(None, None, in_book=False))
    assert all(500 <= delay <= 1500 for delay in samples(None, None, in_book=True))


def test_never_spends_more_than_half_of_the_remaining_time():
    assert all(delay <= 2000 for delay in samples(LONG, 4000, in_book=False))


def test_bullet_pace_never_spends_too_much():
    bullet = TIME_CONTROLS["3i2"]
    assert all(delay <= 10_000 for delay in samples(bullet, 20_000, in_book=False))
    assert all(delay <= 500 for delay in samples(bullet, 1000, in_book=False))


def test_engine_budget_follows_the_clock():
    assert engine_budget_s(None, None) is None
    assert engine_budget_s(TIME_CONTROLS["5"], 30_000) == 1.0
    assert engine_budget_s(TIME_CONTROLS["5"], 300) == 0.01
    assert engine_budget_s(TIME_CONTROLS["3i2"], 60_000) == 3.0
    assert engine_budget_s(TIME_CONTROLS["25d10"], 60_000) == 7.0


def test_limit_uses_the_shorter_of_level_and_budget():
    level = Level("x", {}, chess.engine.Limit(time=1.0))
    assert limit_for(level, None).time == 1.0
    assert limit_for(level, 0.2).time == 0.2
    assert limit_for(level, 5.0).time == 1.0
    deep = Level("y", {}, chess.engine.Limit(depth=2))
    assert limit_for(deep, 0.2).time == 0.2
    assert limit_for(deep, 0.2).depth == 2
