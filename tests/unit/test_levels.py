"""The levels file: every level is defined, with its nominal rating."""

from pathlib import Path

import pytest

from app.config import Settings
from app.engine.levels import LEVEL_ORDER, load_levels


def test_every_level_has_a_rating():
    """The shipped file defines every level in order, each with a non-empty `elo`."""
    levels = load_levels(Settings().levels_file)
    assert list(levels) == list(LEVEL_ORDER)
    assert all(level.elo for level in levels.values())


def test_a_level_without_a_rating_is_refused(tmp_path: Path):
    """A level without `elo` stops the load, so the app does not start with it.

    Args:
        tmp_path (Path): A scratch directory for the broken file.
    """
    text = Settings().levels_file.read_text(encoding="utf-8").replace('elo = "2600"\n', "")
    broken = tmp_path / "levels.toml"
    broken.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="master needs an `elo`"):
        load_levels(broken)
