# Contributing

Thanks for your interest in contributing to Chess Trainer!

## Before you start

Read [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md). It is the spec: behavior, visual design,
architecture, book rules, database, languages and engine. [CLAUDE.md](CLAUDE.md) has the commands
and conventions in short. If something is unclear or contradicts the code, open an issue and ask
before writing code.

## Getting started

1. Fork the repository and clone your fork.
2. Create a branch from an up-to-date `main`.
3. Run the app with `docker compose up --build` and open <http://127.0.0.1:8000>.
4. For development without Docker, install [uv](https://docs.astral.sh/uv/) and run `uv sync`.

## Checks

Run these before opening a pull request:

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run python -m catalog.validate
uv run codespell
```

[CLAUDE.md](CLAUDE.md) lists the engine, image, browser and text checks. A change to the UI is
tested in a browser at 1280x720, the smallest supported screen; say in the pull request what you
tested.

## Rules

- Code, identifiers, comments, commits and docs are in English. User-facing text goes through
  `web/i18n/{locale}.json`, in English, Brazilian Portuguese and Spanish.
- Chess notation is always English SAN.
- No build step, no Node and no CDN: everything the app loads ships in the image.
- Never change or reuse a line `id` in `openings/`. Every book move is validated by tests, and a new
  line records where it came from in `source`.
- Schema changes are new numbered migrations in `app/db/migrations/`. Never delete data without
  a migration.
- No statistics: this is a training tool.
- Third-party assets must be compatible with GPL-3.0 and listed in
  [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Translations

Translations other than English, Portuguese and Spanish are machine-made and unreviewed.
Corrections are welcome. Open a [Translation fix issue](https://github.com/nielsencampos/chess-trainer/issues/new?template=translation-fix.yml).

What differs per language is data, described in
[docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) §8:

- `i18n/locales.toml`, the locale registry: direction, scripts, LanguageTool code, Vale styles
  and whether the author reviews the language. Every `web/i18n/{locale}.json` has an entry there.
- `i18n/glossary/{locale}.toml`: the chess terms of that language, each with the Wikipedia or
  Wikidata page it came from, or `machine = true` when none has it.
- `i18n/names/{locale}.toml`: where each localized opening name in `openings/` came from: a
  Wikipedia or Wikidata page, the glossary (`rule = true`) or machine translation
  (`machine = true`).

Look up a chess term or an opening name in that language's Wikipedia first, and translate by
machine only what it does not have. The fallback is always English (US).

In a translation pull request, reference the correction issue with `Fixes #n` and update the
glossary or opening-name source record that the changed translation relies on, as applicable.

## Pull requests

Keep them small, one subject each, with small commits. Describe what changed and how to test it.
By contributing, you agree that your work is licensed under GPL-3.0, like the project.

## Code of Conduct

This project follows its [Code of Conduct](CODE_OF_CONDUCT.md).
