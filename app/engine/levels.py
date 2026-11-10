"""Strength levels, configured in a file (brief §9)."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

import chess.engine

LEVEL_ORDER = ("warmup", "club", "strong", "max")


@dataclass(frozen=True)
class Level:
    """One bot strength level.

    Attributes:
        key (str): The level's key, one of `LEVEL_ORDER`.
        options (dict[str, int | bool]): UCI options set while the bot plays, such as `Skill Level`.
        limit (chess.engine.Limit): How long or deep the bot searches.
    """

    key: str
    options: dict[str, int | bool]
    limit: chess.engine.Limit


def load_levels(path: Path) -> dict[str, Level]:
    """Reads the strength levels from a TOML file.

    Args:
        path (Path): The levels file, with a `[levels.<key>]` table per level.

    Returns:
        dict[str, Level]: The levels by key, in `LEVEL_ORDER`.

    Raises:
        ValueError: The file does not define exactly the levels in `LEVEL_ORDER`.
    """
    with path.open("rb") as handle:
        raw = tomllib.load(handle)["levels"]
    if set(raw) != set(LEVEL_ORDER):
        raise ValueError(f"{path}: levels must be exactly {LEVEL_ORDER}, got {sorted(raw)}")
    limit_keys = {"depth": "depth", "nodes": "nodes", "movetime": "time"}
    return {
        key: Level(
            key=key,
            options=raw[key]["options"],
            limit=chess.engine.Limit(
                **{limit_keys[name]: value for name, value in raw[key]["limit"].items()}
            ),
        )
        for key in LEVEL_ORDER
    }
