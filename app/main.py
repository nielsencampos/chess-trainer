"""FastAPI application: mounts the API and serves web/. Run with `--factory`."""

import random
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.book.loader import load_book
from app.config import Settings, settings_from_env
from app.engine.levels import load_levels
from app.engine.process import MoveEngine, StockfishEngine
from app.game.service import GameService


def create_app(
    settings: Settings | None = None,
    engine: MoveEngine | None = None,
    rng: random.Random | None = None,
) -> FastAPI:
    settings = settings or settings_from_env()
    # Fails loudly on a bad repertoire: the app must not start with one.
    book = load_book(settings.repertoire_dir)
    levels = load_levels(settings.levels_file)
    engine = engine or StockfishEngine(
        settings.stockfish_path,
        settings.stockfish_threads,
        settings.stockfish_hash_mb,
        settings.stockfish_version_file,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await engine.start()
        yield
        await engine.stop()

    app = FastAPI(title="chess-trainer", version=__version__, lifespan=lifespan)
    app.state.games = GameService(book, engine, levels, rng)
    app.include_router(router)
    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app
