"""Runtime settings, read from the environment with defaults that fit the Docker image."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent


@dataclass(frozen=True)
class Settings:
    openings_dir: Path = ROOT / "openings"
    catalog_dir: Path = ROOT / "catalog" / "data"
    book_evals_file: Path = ROOT / "evals" / "book.json"
    database_path: Path = ROOT / "data" / "chess-trainer.duckdb"
    web_dir: Path = ROOT / "web"
    levels_file: Path = Path(__file__).parent / "engine" / "levels.toml"
    stockfish_path: str = "stockfish"
    stockfish_version_file: Path = Path("/opt/stockfish/VERSION")
    stockfish_threads: int = 2
    stockfish_hash_mb: int = 128


def settings_from_env() -> Settings:
    defaults = Settings()
    return Settings(
        openings_dir=Path(os.environ.get("CHESS_TRAINER_OPENINGS_DIR", defaults.openings_dir)),
        catalog_dir=Path(os.environ.get("CHESS_TRAINER_CATALOG_DIR", defaults.catalog_dir)),
        book_evals_file=Path(os.environ.get("CHESS_TRAINER_BOOK_EVALS", defaults.book_evals_file)),
        database_path=Path(os.environ.get("CHESS_TRAINER_DB", defaults.database_path)),
        web_dir=Path(os.environ.get("CHESS_TRAINER_WEB_DIR", defaults.web_dir)),
        levels_file=Path(os.environ.get("CHESS_TRAINER_LEVELS_FILE", defaults.levels_file)),
        stockfish_path=os.environ.get("STOCKFISH_PATH", defaults.stockfish_path),
        stockfish_threads=int(os.environ.get("STOCKFISH_THREADS", defaults.stockfish_threads)),
        stockfish_hash_mb=int(os.environ.get("STOCKFISH_HASH_MB", defaults.stockfish_hash_mb)),
    )
