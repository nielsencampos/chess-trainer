---
name: add-opening
description: Add an opening or variations to the repertoire from a pasted PGN, a file or a Lichess study. Normalizes headers, generates VariantIds, validates against python-chess and the catalog, runs tests and opens a PR. Use when asked to add, import or extend repertoire lines.
---

# Add an opening

Rules are in `docs/PROJECT_BRIEF.md` §6 and §13. Do not invent theory moves: every line comes from
the given PGN or the catalog, and its origin goes in `[Source]`. Check a site's terms before copying
lines into this public repository.

1. **Get the lines.** One `.pgn` per opening in `repertoire/`, and each game is one variation. RAVs
   are allowed and become book branches.
2. **Write the headers** on every game: `RepertoireId`, `RepertoireName_en`, `VariantId`, `Color`
   (the user's color), `Name_en`, `Source`, `Result "*"`. Add `ECO` and `Opening` when the final
   position is in the catalog: find them by position with `catalog.loader`, not from memory.
3. **Generate `VariantId`s** as `<repertoire-id>.<group>.<line>` in lowercase with hyphens.
   Never change or reuse an existing `VariantId`: statistics are keyed on it.
4. **Validate:**
   ```bash
   uv run python -m catalog.validate
   uv run pytest
   ```
   Update the expected counts and colors in `tests/unit/test_repertoire.py`.
5. **Show the user** the variations (id, ECO, moves, name) and wait for approval before committing.
6. **Open a PR** from a new branch, listing the lines and their sources. Say which lines end on the
   bot's move, because the user's next move there is not checked.
