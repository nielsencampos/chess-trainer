# chess-trainer

Local, single-user opening trainer. A bot plays your repertoire lines at random and
Stockfish takes over when theory ends. Python backend, plain-JS frontend, one Docker image.

**Read [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) before changing anything.** It is the
spec: behavior (§4), visual design (§4.1), architecture (§5), repertoire rules (§6), database
(§7), i18n (§8), engine (§9), phases (§12) and working rules (§13). If something is unclear or
contradicts the code, ask instead of inventing.

## Run

```bash
docker compose up --build        # http://127.0.0.1:8000
docker compose build --pull      # update Python base image and Stockfish
```

Local development without Docker needs a Stockfish binary (see "Test"):

```bash
uv sync
STOCKFISH_PATH=/path/to/stockfish uv run uvicorn --factory app.main:create_app --reload
```

## Test

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest                                     # unit + API, uses a fake engine
uv run python -m catalog.validate                 # every repertoire line against the catalog
scripts/extract-stockfish.sh                      # copies the binary from the image to .cache/
STOCKFISH_PATH=.cache/stockfish uv run pytest -m engine
scripts/smoke.sh chess-trainer:local              # health and a real engine move in the image
E2E_BASE_URL=http://127.0.0.1:8000 uv run pytest -m e2e   # Playwright, desktop and mobile
```

Before calling UI work done, test it in a browser at desktop and mobile viewports and state
what was tested (brief §13.4).

## Conventions

- Code, identifiers, comments, commits and docs are in English.
- User-facing text goes through i18n: `web/i18n/{locale}.json` keys, never hard-coded strings.
- Chess notation is always English SAN, in every language.
- No build step and no Node. No CDN: everything the app loads ships in the image.
- Uvicorn runs with a single worker. Do not change this (DuckDB allows one writing process).
- Python: ruff for lint and format, type hints on public functions. JS: ES modules, JSDoc types.
- Small commits. One phase at a time; at the end of each, report what changed, how to test it
  and what was left for later.

## Repertoire rules

- **Never change or reuse a `VariantId`.** Statistics are keyed on it.
- Never delete database data without a migration and a note.
- Every repertoire move is validated by tests, never by memory. Do not invent theory moves:
  lines come from the catalog or a source recorded in `[Source]`.
- `[Name_en]` is the UI label. `[Opening]` is the exact catalog name and is what gets validated.
- The Lichess catalog is not the bot's book. The bot plays only repertoire variations.
- Third-party assets must be compatible with GPL-3.0 and listed in `THIRD_PARTY_LICENSES.md`.
