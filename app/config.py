"""Runtime settings, read from the environment with defaults that fit the Docker image."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent


@dataclass(frozen=True)
class Settings:
    repertoire_dir: Path = ROOT / "repertoire"
    web_dir: Path = ROOT / "web"
    levels_file: Path = Path(__file__).parent / "engine" / "levels.toml"
    stockfish_path: str = "stockfish"
    stockfish_version_file: Path = Path("/opt/stockfish/VERSION")
    stockfish_threads: int = 2
    stockfish_hash_mb: int = 128


def settings_from_env() -> Settings:
    defaults = Settings()
    return Settings(
        repertoire_dir=Path(
            os.environ.get("CHESS_TRAINER_REPERTOIRE_DIR", defaults.repertoire_dir)
        ),
        web_dir=Path(os.environ.get("CHESS_TRAINER_WEB_DIR", defaults.web_dir)),
        levels_file=Path(os.environ.get("CHESS_TRAINER_LEVELS_FILE", defaults.levels_file)),
        stockfish_path=os.environ.get("STOCKFISH_PATH", defaults.stockfish_path),
        stockfish_threads=int(os.environ.get("STOCKFISH_THREADS", defaults.stockfish_threads)),
        stockfish_hash_mb=int(os.environ.get("STOCKFISH_HASH_MB", defaults.stockfish_hash_mb)),
    )
