"""Runtime settings, read from the environment with defaults that fit the Docker image."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent


@dataclass(frozen=True)
class Settings:
    """Where the app finds its files and how it starts Stockfish.

    Attributes:
        openings_dir (Path): The book source, `openings/`.
        catalog_dir (Path): The pinned Lichess catalog files.
        book_evals_file (Path): The book evaluations, `evals/book.json`.
        database_path (Path): The DuckDB file.
        web_dir (Path): The frontend served at `/`.
        levels_file (Path): The bot strength levels (TOML).
        stockfish_path (str): The Stockfish binary, a path or a name on `PATH`.
        stockfish_version_file (Path): The `VERSION` file written by the image build.
        stockfish_threads (int): Stockfish's `Threads` option.
        stockfish_hash_mb (int): Stockfish's `Hash` option, in MB.
    """

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
    """Reads the settings from `CHESS_TRAINER_*` and `STOCKFISH_*` variables.

    Returns:
        Settings: The settings, with the defaults for every variable that is not set.
    """
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
