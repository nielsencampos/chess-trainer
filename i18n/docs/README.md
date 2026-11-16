<p align="center">
  <img src="web/logo.svg" alt="{{readme.logo}}" width="160">
</p>

# Chess Trainer

{{languages}}

{{notice}}

{{readme.intro}}

[![CI](https://github.com/nielsencampos/chess-trainer/actions/workflows/ci.yml/badge.svg)](https://github.com/nielsencampos/chess-trainer/actions/workflows/ci.yml)
[![Desktop](https://github.com/nielsencampos/chess-trainer/actions/workflows/desktop.yml/badge.svg)](https://github.com/nielsencampos/chess-trainer/actions/workflows/desktop.yml)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.1+-yellow.svg)](https://duckdb.org/)
[![Stockfish](https://img.shields.io/badge/Stockfish-latest-lightgrey.svg)](https://stockfishchess.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Claude](https://img.shields.io/badge/Claude-claude--code-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)

{{readme.reviewed}}

## {{readme.run.title}}

{{readme.run.needs}}

```bash
git clone https://github.com/nielsencampos/chess-trainer.git
cd chess-trainer
docker compose up --build
```

{{readme.run.open}}

{{readme.run.image}}

```bash
mkdir -p data
docker run -d --init --name chess-trainer -p 127.0.0.1:8000:8000 \
  -v "$PWD/data:/app/data" ghcr.io/nielsencampos/chess-trainer:latest
```

{{readme.run.network}}

{{readme.run.desktop}}

## {{readme.how.title}}

{{readme.how.guide}}

1. {{readme.how.pick}}
2. {{readme.how.bot}}
3. {{readme.how.deviation}}
4. {{readme.how.engine}}

{{readme.how.hide}}

{{readme.beyond.title}}

- {{readme.beyond.clocks}}
- {{readme.beyond.chess960}}
- {{readme.beyond.saved}}
- {{readme.beyond.import}}
- {{readme.beyond.eval}}
- {{readme.beyond.sheet}}
- {{readme.beyond.help}}

{{readme.fairPlay}}

{{readme.state}}

## {{readme.book.title}}

{{readme.book.text}}

{{readme.book.data}}

## {{readme.stockfish.title}}

{{readme.stockfish.latest}}

```bash
docker compose build --pull
docker compose up -d
```

{{readme.stockfish.pin}}

```bash
STOCKFISH_VERSION=sf_19 docker compose build
```

{{readme.stockfish.version}}

## {{readme.develop.title}}

{{readme.develop.needs}}

```bash
uv sync
uv run pytest
```

{{readme.develop.pictures}}

```bash
uv run python scripts/help_media.py --base-url http://127.0.0.1:8000
```

{{readme.develop.docs}}

## {{readme.license.title}}

{{readme.license.text}}
