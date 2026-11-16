# chess-trainer

Local, single-user opening trainer. A bot plays your repertoire lines at random and
Stockfish takes over when theory ends. Python backend, plain-JS frontend, one Docker image.

**Read [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) before changing anything.** It is the
spec: behavior (§4), visual design (§4.1), architecture (§5), repertoire rules (§6), database
(§7), i18n (§8), engine (§9), phases (§12) and working rules (§13). If something is unclear or
contradicts the code, ask instead of inventing. [docs/SESSION_PROMPT.md](docs/SESSION_PROMPT.md) is the
prompt a contributor pastes at the start of a session with an AI assistant.

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
uv run python -m catalog.validate                 # lines against the catalog, names coverage
uv run codespell                                  # spelling of code, comments and docstrings
scripts/languagetool.sh --background && uv run python scripts/check_text.py   # prose, needs Java 17+
scripts/vale.sh                                   # style: product name, form of address, glossary terms, no English in the UI
uv run python scripts/vale_glossary.py            # Vale styles from i18n/glossary, after a glossary change
scripts/extract-stockfish.sh                      # copies the binary from the image to .cache/
python3 docker/fetch_stockfish.py desktop         # or: this system's official binary into .cache/
uv run python scripts/desktop_smoke.py build/dist/chess-trainer/chess-trainer   # after a desktop build
STOCKFISH_PATH=.cache/stockfish uv run pytest -m engine
scripts/smoke.sh chess-trainer:local              # health and a real engine move in the image
E2E_BASE_URL=http://127.0.0.1:8000 uv run pytest -m e2e   # Playwright, desktop
uv run python scripts/help_media.py                       # Help pictures, after a visible UI change
uv run python scripts/help_docs.py                        # docs/HELP*.md, after a Help text change
uv run python scripts/readme_docs.py                      # README*.md, HOW_TO_INSTALL*.md, after an i18n/docs change
```

Before calling UI work done, test it in a browser at 1280x720 and state what was tested. HD is
the smallest supported screen, and mobile is out of scope.

## Conventions

- Code, identifiers, comments, commits and docs are in English.
- User-facing text goes through i18n: `web/i18n/{locale}.json` keys, never hard-coded strings. The
  README and the install guide are generated from `i18n/docs/` in every language, and `docs/HELP*.md` and
  `docs/ABOUT*.md` from the Help and About strings; edit those, not the `.md`.
  Per-locale settings live in `i18n/locales.toml`, chess terms in `i18n/glossary/`, and where each
  localized opening name came from in `i18n/names/` (brief §8). The fallback is always `en-US`.
- PGN, imports, stored moves and `openings/*.json` are always English SAN, in every language. The
  screen follows the player's notation (figurines, English letters or the UI language's letters,
  `web/js/notation.js`, brief §8); piece letters per locale live in the glossaries.
- No build step and no Node. No CDN: everything the app loads ships in the image.
- Uvicorn runs with a single worker. Do not change this (DuckDB allows one writing process).
- Python: ruff for lint and format, type hints on public functions, and a Google-style docstring
  (description, Args, Returns, Raises) on every module, class and function, checked by ruff.
- JS: ES modules, and JSDoc (description, `@param`, `@returns`) on every function, method and class.
- Small commits. One phase at a time; at the end of each, report what changed, how to test it
  and what was left for later.

## Book rules

- `openings/<group>/[others/]<family>.json` is the source of the book (format in brief §6). The app reads the book
  only from DuckDB. `catalog/` is reference only: the bot does not play from it.
- **Never change or reuse a line `id`**, even when extending its moves. Saved games and their PGN (`VariantId`) refer to it.
  Lines that disappear become inactive and are never deleted.
- Never delete database data without a migration and a note. Schema changes are new numbered files
  in `app/db/migrations/`.
- Localized opening names come from `uv run python -m catalog.names <locale>` (brief §8): Wikipedia
  first, then the glossary, then machine translation, each recorded in `i18n/names/{locale}.toml`.
- Every book move is validated by tests, never by memory. Do not invent theory moves, and record
  where a line came from in `source`.
- Third-party assets must be compatible with GPL-3.0 and listed in `THIRD_PARTY_LICENSES.md`.
