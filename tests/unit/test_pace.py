import random

from app.game.pace import TIME_CONTROLS, human_delay_ms

LONG = TIME_CONTROLS["45+30"]
BLITZ = TIME_CONTROLS["3+2"]


def samples(time_control, remaining, in_book):
    rng = random.Random(1)
    return [human_delay_ms(time_control, remaining, in_book, rng) for _ in range(500)]


def test_45_30_out_of_book_is_about_60_to_100_seconds():
    delays = samples(LONG, LONG.base_ms, in_book=False)
    assert min(delays) >= 60_000 and max(delays) <= 100_000


def test_45_30_in_book_is_about_5_to_15_seconds():
    delays = samples(LONG, LONG.base_ms, in_book=True)
    assert min(delays) >= 4_500 and max(delays) <= 15_000


def test_blitz_is_much_faster():
    assert max(samples(BLITZ, BLITZ.base_ms, in_book=False)) < 8_000


def test_no_clock_uses_fixed_ranges():
    assert all(2000 <= delay <= 6000 for delay in samples(None, None, in_book=False))
    assert all(500 <= delay <= 1500 for delay in samples(None, None, in_book=True))


def test_never_spends_more_than_half_of_the_remaining_time():
    assert all(delay <= 2000 for delay in samples(LONG, 4000, in_book=False))
