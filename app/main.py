"""FastAPI application: mounts the API and serves web/. Run with `--factory`."""

import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.book.sync import (
    load_book,
    load_book_evals,
    load_opening_names,
    sync_book_evals,
    sync_catalog,
    sync_openings,
)
from app.config import Settings, settings_from_env
from app.db.connection import apply_migrations, open_database
from app.engine.evaluation import Evaluator
from app.engine.levels import load_levels
from app.engine.process import MoveEngine, StockfishEngine
from app.game.remote import fetch_url
from app.game.service import GameService
from app.game.store import GameStore


def create_app(
    settings: Settings | None = None,
    engine: MoveEngine | None = None,
    rng: random.Random | None = None,
) -> FastAPI:
    """Builds the app: opens the database, loads the book and wires the services.

    Fails loudly, so the app does not start, on a bad database, opening file or levels file.

    Args:
        settings (Settings | None): Where the files are; read from the environment when None.
        engine (MoveEngine | None): The engine; a real Stockfish process when None.
        rng (random.Random | None): The random source for the draws; tests pass a seeded one.

    Returns:
        FastAPI: The app, with the API under `/api` and `web/` served at `/`.
    """
    settings = settings or settings_from_env()
    # Fails loudly on a bad database or opening file: the app must not start with one.
    database = open_database(settings.database_path)
    apply_migrations(database)
    sync_openings(database, settings.openings_dir)
    sync_catalog(database, settings.catalog_dir)
    sync_book_evals(database, settings.book_evals_file)
    book = load_book(database)
    opening_names = load_opening_names(database)
    levels = load_levels(settings.levels_file)
    engine = engine or StockfishEngine(
        settings.stockfish_path,
        settings.stockfish_threads,
        settings.stockfish_hash_mb,
        settings.stockfish_version_file,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Starts the engine with the app, then stops it and closes the database.

        Args:
            app (FastAPI): The app being run.

        Yields:
            None: Control while the app runs.
        """
        await engine.start()
        yield
        await engine.stop()
        database.close()

    app = FastAPI(title="chess-trainer", version=__version__, lifespan=lifespan)
    app.state.evaluator = Evaluator(engine, load_book_evals(database))
    app.state.games = GameService(book, engine, levels, GameStore(database), rng, opening_names)
    app.state.database = database
    app.state.fetch_url = fetch_url
    app.state.i18n_dir = settings.web_dir / "i18n"
    app.include_router(router)
    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app
