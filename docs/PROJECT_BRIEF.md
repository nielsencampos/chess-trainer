# chess-trainer — Project Brief

> **Status:** living document. It describes what the project is, how it is built and the order in which it gets built. Open decisions are marked ⚠️ (see §11).
> **For contributors and AI agents:** read this file before changing anything. If something here is unclear or contradicts the code, ask before inventing.

**Repository:** `chess-trainer` (public, GPL-3.0)
**Description:** Local opening trainer: drill your chess repertoire against a bot that plays your book lines, then Stockfish when theory ends. Python + DuckDB + plain JS, all in one Docker image.
**Topics:** `chess` `chess-openings` `opening-trainer` `stockfish` `python-chess` `fastapi` `duckdb` `docker`

---

## 1. Context

chess-trainer is an **open-source opening trainer** you run on your own machine. You pick a color and the openings/variations you want to drill; a bot plays the book lines at random, and when theory ends (or someone leaves it) Stockfish takes over. Every game is recorded so you can see where you leave theory and which lines you know.

It started as a personal single-file HTML prototype. This project rebuilds it from scratch as a modular application: Python backend, plain JavaScript frontend, Stockfish and DuckDB, all in one Docker image. The prototype is **not** part of the repository; §4 and §4.1 are the full specification of the expected behavior and look.

**Scope:** a **local, single-user** app. Everyone clones it and runs `docker compose up` on their own machine. No central server, no accounts, no login. By default the app listens on `127.0.0.1` only.

**Target user:** club and online players (roughly 800–1800) who want to drill their repertoire with long time controls, optionally writing moves on a paper scoresheet.

## 2. Goals

1. Implement everything described in §4 and §4.1.
2. Split it into modules: Python backend, ES-module JavaScript frontend, book in JSON files loaded into DuckDB.
3. Run with `docker compose up` from a single image containing Python, Stockfish and the frontend.
4. Store repertoire, games and statistics in a local DuckDB file (no browser storage for data).
5. UI and opening names in **English and Brazilian Portuguese (pt-BR)**, structured so new languages (Spanish is next) need no code changes.

## 3. Stack (decided)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.12+, FastAPI, Uvicorn | **Single worker** (DuckDB allows one writing process per file) |
| Rules / PGN | python-chess | Parses PGN with variations, validates moves, renders SVG for reports |
| Engine | Stockfish (official binary, **latest release**) | Driven through `chess.engine` (async) |
| Database | DuckDB (local file in `./data`) | Repertoire and translations, games, deviations, stats, settings |
| Frontend | Plain HTML + CSS + JS, ES modules, **no build step, no Node** | Types via JSDoc. chess.js and piece sets are vendored, no CDN |
| Python packaging | uv (`pyproject.toml` + `uv.lock`) | |
| Container | Multi-stage Dockerfile + `docker-compose.yml` | Slim final image, non-root user, healthcheck |
| Tests | pytest (backend), Playwright (browser flows) | |
| CI | GitHub Actions: ruff, tests, repertoire validation, image build | |

## 4. Required behavior

- The bot picks at random among the next book moves. When theory ends or someone leaves it, the engine takes over at the selected strength.
- Color selection (White/Black), selected openings and **selected variations** (a collapsible multi-select per opening). Each selected variation has the same chance of being drawn.
- Theory = selected variations only. Playing a move from an unselected variation counts as a deviation.
- User deviations are recorded with the expected move(s) and shown at the end of the game.
- Clock with increment. Bullet: 20s+1, 30s+0, 1+0, 1+1, 2+1. Blitz: 3+0, 3+2, 5+0, 5+3. Rapid: 10+0, 10+5, 15+10, 20+0, 30+0, 60+0. Classical: 90 + 30 min with 30 s and 45 + 15 min with 15 s, where the extra minutes are added on completing move 40 and the increment runs from move 1. Or no clock. The groups are for training and do not follow FIDE's categories exactly.
- The engine never searches for longer than the bot's clock allows. Bot response time "Instant" or "Human" (human-like, based on the clock).
- Scoresheet mode (hides the move list so you write on paper), offered only for classical and no clock, out-of-theory warning, auto-play next game.
- End of game: result, variation, how far theory went, deviations, copy PGN, link to Lichess analysis.
- Green/cream board (a1 is dark), SVG piece sets with a picker (Merida, Cburnett, Chessnut, Fantasy, Unicode), light and dark theme, mobile layout, click **and** drag to move.
- Board flips to the user's color. Coordinates on the left file and bottom rank. Highlights: last move, selected square, legal targets (dot; ring for captures), king in check.
- Promotion picker (Q/R/B/N) as an overlay on the board.
- Resign needs a second click to confirm (no browser dialogs).

### 4.1 Visual specification

Layout: board column on the left, a 380 px side panel on the right (setup card, game card with the move list, end-of-game card). Below 900 px wide, a single column. Bot name and clock above the board, user name and clock below, status chips under the board ("Your move", "In theory", "Left theory at move N", "Check").

Design tokens (CSS custom properties):

| Token | Light | Dark |
|---|---|---|
| `--bg` | `#eef1ea` | `#121814` |
| `--surface` / `--surface-2` | `#ffffff` / `#f6f8f3` | `#1a221d` / `#202a24` |
| `--ink` / `--muted` | `#18201b` / `#5a6a60` | `#e6ece7` / `#9aaa9f` |
| `--line` | `#d3dbd0` | `#2f3b34` |
| `--accent` / `--accent-soft` | `#2d6a3e` / `#dcebdd` | `#78b884` / `#233528` |
| `--warn` / `--bad` | `#a8641c` / `#b03c2c` | `#e0a35c` / `#e9806f` |
| board light / dark | `#eeeed2` / `#769656` | same |
| last move / selected | `rgba(246,246,105,.55)` / `.8` | same |

- Fonts (Google Fonts, vendored): Familjen Grotesk (UI), JetBrains Mono (clocks, move list, numbers).
- Theme follows `prefers-color-scheme`, with a manual override.
- Clock turns accent-colored on the side to move and red under 20 s or 10% of the starting time, whichever is less.
- Move list in scoresheet style: numbered rows, white and black columns, out-of-theory moves in `--warn`, the user's deviation in bold `--bad`.

## 5. Architecture

```
chess-trainer/
├── app/
│   ├── main.py            # FastAPI: mounts the API and serves web/
│   ├── api/               # routes: repertoire, games, engine, stats, settings
│   ├── book/              # opening files → DuckDB sync, book read from the database
│   ├── game/              # variation draw, theory tracking, bot pace, final report
│   ├── engine/            # Stockfish process, strength levels
│   ├── db/                # DuckDB connection, versioned SQL migrations
│   └── i18n/              # backend strings (if any)
├── openings/              # the book: one JSON per opening family (§6)
├── catalog/               # pinned Lichess catalog, reference only: seed and validation (§6)
├── data/                  # chess-trainer.duckdb, bind-mounted, not versioned (§7)
├── web/
│   ├── index.html
│   ├── css/
│   ├── js/                # board.js, clock.js, game.js, api.js, i18n.js, setup.js…
│   ├── i18n/              # en.json, pt-BR.json
│   └── pieces/            # SVG piece sets (licenses in THIRD_PARTY_LICENSES.md)
├── docs/                  # this brief and other docs
├── tests/                 # pytest + Playwright
├── .claude/               # project skills (§10)
├── CLAUDE.md
├── Dockerfile
├── docker-compose.yml
├── LICENSE                # GPL-3.0
├── THIRD_PARTY_LICENSES.md
└── README.md              # English, with a pt-BR section
```

**Responsibilities**
- **Browser:** board, move input, clock, screens. Validates moves locally with chess.js for instant feedback.
- **Server:** source of truth for the repertoire, variation draw, bot moves (book or Stockfish), game recording.
- Everything ships in the container: FastAPI serves `web/`, so JS, CSS and piece sets come from the image. Nothing loads from a CDN; the app works without internet.

## 6. The book: our JSON files in git, DuckDB as the working store

**Decision (2026-11-07):** every opening of the Lichess catalog is available to drill, in our own format. Any line can be drilled with either color: the color is chosen in the setup, not stored with the line.

"Source → serving layer":
- **Source (versioned in git):** `openings/<family>.json`, one file per opening family, 149 at the start. They are ours: lines can be edited, extended or removed through PRs.
- **Working store (DuckDB):** on startup the backend loads these files into tables (§7). The app reads the book only from the database.
- **User lines (next step):** openings imported from the UI (paste PGN, Lichess study) go through the same validation into the database with `source = 'user'`, and can be exported to JSON. A sync never touches them.
- Loading is idempotent: only changed files are reloaded (file hash). A failed load changes nothing.

File format:

```json
{
  "id": "caro-kann-defense",
  "names": { "en": "Caro-Kann Defense", "pt-BR": "Defesa Caro-Kann" },
  "lines": [
    {
      "id": "line-3f2a9c10b7d4e681",
      "names": { "en": "Advance Variation, Short Variation" },
      "eco": "B12",
      "opening": "Caro-Kann Defense: Advance Variation, Short Variation",
      "moves": ["e4", "c6", "d4", "d5", "e5", "Bf5", "Nf3"],
      "source": "lichess-org/chess-openings@3ba6b20 (CC0-1.0)"
    }
  ]
}
```

- `id` (family) must match the file name. `names.en` is required and is the fallback; other locales are optional.
- `id` (line) is stored and **never changes**, even if the moves are extended, because statistics are keyed on it. A line that disappears becomes `active = false` and is never deleted.
- `eco` and `opening` are optional. `opening` is the exact catalog name of the line's final position and is validated against the catalog. A line we extended or imported drops it, or it fails validation.
- `moves` is a flat list of SAN moves. There are no side variations: an alternative is another line, so each one has the same chance in the draw.

**Lichess catalog** (`lichess-org/chess-openings`, CC0), pinned in `catalog/`, is **reference only**. The bot does not play from it. It is used to:
1. Seed `openings/` once, with `catalog/generate_openings.py`.
2. Validate `eco` and `opening`, matching by position (EPD), because catalog names repeat and lines transpose (`catalog/validate.py`).
3. Name any position (still to do): during and after the game, show the most specific opening name matching the moves.

A newer catalog does not enter by itself: comparing it with `openings/` and accepting the differences through a PR is still to be built.

**Known limit:** the catalog lists named positions, not repertoire replies, so seeded lines are often short, can end on either side's move and include offbeat gambits. Nothing is selected by default; the user picks what to drill, with search by name, ECO or moves.

**Selection and draw**
- A book is a set of positions (EPD) with their moves, so transpositions are recognized.
- At game start one selected variation is drawn with equal chance, and the bot follows it.
- If the user plays a move from another selected variation, the bot redraws among the selected variations containing that position.
- When the drawn variation ends, the engine takes over, even if another selected variation continues.
- Theory is the union of the selected variations. A user move outside it, when that union has a move for the position, is a deviation. Once out of theory a game does not return to it.

Loading **fails loudly** on an illegal move or an empty book: the app does not start.

## 7. Database (DuckDB)

Local file `data/chess-trainer.duckdb`, bind-mounted (`./data`) so it is visible on the host and easy to back up. Numbered SQL migrations (`app/db/migrations/001_init.sql`…), applied on startup.

Repertoire tables:
- `catalog_loads` — content_hash, source_commit, loaded_at
- `repertoires` — repertoire_id (catalog family), source (`catalog`/`user`), file_path, file_hash, loaded_at
- `variants` — variant_id, repertoire_id, eco, opening (catalog name), pgn, moves_san (list), final_epd, source, active
- `names` — entity_type (`repertoire`/`variant`/`catalog`), entity_id, locale, name. Translations live here.
- `book_moves` — repertoire_id, variant_id, epd_before, ply, uci, san. The book tree, flattened for fast lookup.
- `openings_catalog` — eco, name (en), pgn, uci, epd (final position), source_commit

Usage tables:
- `games` — id, started_at, ended_at, repertoire_id, variant_id (drawn), user_color, time_control, bot_level, bot_pace, result (win/draw/loss), termination, theory_until_ply, total_plies, pgn, app_version, engine_version
- `moves` — game_id, ply, san, uci, fen_before, by (`user`/`bot`), source (`book`/`engine`), clock_ms_after, think_ms
- `deviations` — game_id, ply, played_san, expected_san (list)
- `settings` — key, value (JSON)
- Stats views: W/D/L per repertoire and per variation, deviation rate per variation and per move, average think time inside theory.

Rules:
- One connection per process, one cursor per request. Uvicorn runs with `--workers 1`.
- Export endpoint (CSV/Parquet); backup procedure documented in the README.

## 8. Internationalization

- UI strings in `web/i18n/{locale}.json` with stable keys (`setup.play`, `end.deviation`…).
- Opening and variation names come from the `names` table (loaded from `Name_<locale>` PGN tags), falling back to `en`.
- Default locale `en`, switchable in the UI, stored in `settings`.
- Move notation: **always English SAN**, in every language (PGN, Lichess and Chess.com standard). Possible future option: figurine notation.
- Adding a language = one JSON file plus `Name_<locale>` tags, no code changes.

## 9. Engine

- **Always the latest Stockfish.** The Dockerfile resolves the newest official release (GitHub `official-stockfish/Stockfish`, `releases/latest`) at build time and downloads the right binary for the architecture (amd64, arm64). Since `sf_19` the official binaries are *universal*: they detect the CPU at run time, so there is no flavor to pick.
- A build arg `STOCKFISH_VERSION` defaults to `latest` and can be set to a specific tag to reproduce an old build or work around a bad release. Only `sf_19` or newer is accepted (older releases have no universal binary and no Linux arm64 build); anything older fails the build with a clear message.
- The resolved version is recorded: `/api/health` and a `VERSION` file in the image are the authority, shown in the UI footer, and stored per game (`games.engine_version`), so stats can be compared across engine versions. The image label holds the version that was requested, because a `LABEL` is fixed before the download runs; it names a real version only when a tag is passed explicitly (as CI does).
- Updating = rebuilding the image (`docker compose build --pull`). A scheduled CI job (weekly) rebuilds and runs the tests against the newest release, so a breaking Stockfish change is caught early.
- Four levels (Warm-up, Club, Strong, Max) mapped to `Skill Level` + depth/movetime, configurable in a file. Evaluate `UCI_LimitStrength`/`UCI_Elo` for a ~1200 level; note `UCI_Elo` has a floor (around 1320 in recent versions).
- One long-lived Stockfish process behind a queue: one search at a time.
- The "Human" response time is decided by the backend, based on the clock.

## 10. Claude Code: CLAUDE.md and project skills

- `CLAUDE.md` — overview, how to run, how to test, conventions (code and identifiers in English; user-facing text through i18n), never break a `VariantId`, link to this brief.
- Skills in `.claude/skills/`, none yet:
  - **add-opening** — takes a PGN or Lichess study, writes it in the format of §6, validates, runs tests and opens a PR.
  - **review-catalog** — checks a new catalog commit against `openings/`: what changed and what to accept.
  - **release** — bumps version, changelog, tag and Docker image.
  - **db-migration** — creates the next numbered migration with a test.

## 11. Decisions

**Closed**
- Local, open-source, single-user app, no login. Listens on `127.0.0.1` by default.
- Book: `openings/*.json` in git as source, seeded from the Lichess catalog, DuckDB as working store, translated names in a table. Any line plays with either color.
- Statistics only in the local DuckDB file.
- Built from scratch; the HTML prototype is not in the repository.
- English SAN notation always.
- **License: GPL-3.0.** Compatible with Stockfish and the chosen piece sets. `THIRD_PARTY_LICENSES.md` lists Stockfish, chess.js, the openings catalog, the fonts and each piece set. Lichess's Maestro (CC BY-NC-SA) and Alpha (non-commercial) sets are excluded because of their non-commercial terms.
- Stockfish: always the latest official release, resolved at build time (§9), with an override for a specific version.
- Stockfish runs only in the container. No Stockfish WASM in the browser; the app does not run without the backend.
- Openings catalog: import all of `lichess-org/chess-openings` as reference; `openings/` starts with all of its lines.

**Future sources for user lines** (reviewed case by case)
- Lichess studies exported as PGN.
- Other sites (e.g. chessme.io): check their terms before copying lines into this public repository.

**Open ⚠️**
1. Lichess opening explorer **live** (the bot plays what people at your rating actually play; needs internet) or **reference only** when building PGNs (app stays fully offline)? Default until decided: reference only. Note: the explorer API now requires authentication (HTTP 401 without a token, checked 2026-11-07), so a live mode would need a per-user token.

## 12. Delivery phases

1. **Foundation:** repo layout, Docker, FastAPI serving the frontend (built from §4/§4.1), the book in `openings/*.json` loaded into DuckDB, validation tests. Includes the real Stockfish with provisional levels, because §4 needs it. The book lives in DuckDB. Games live in RAM and UI preferences stay in `localStorage` until Phase 2. UI strings are English only until Phase 4. *Done when: every item in §4 works in the browser (desktop and mobile).*
2. **Data:** opening name on screen, recording of games, moves and deviations, settings on the server.
3. **Engine on the server:** native Stockfish with calibrated levels.
4. **Languages:** complete en and pt-BR, language picker.
5. **Statistics:** per-variation screen (where I deviate most, how far I get in theory, progress over time).
6. **Backlog:** opening-only drill mode, take-back, sounds, PDF report with diagrams.

## 13. Working rules

1. One phase at a time. At the end of each: what changed, how to test it, what was left for later.
2. Every book move is validated by tests, never by memory.
3. Never change a `VariantId` or delete database data without a migration and a note.
4. Test in a browser (desktop and mobile viewport) before calling something done, and state what was tested.
5. If anything in this brief is ambiguous or conflicting, ask before inventing.
