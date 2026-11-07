---
name: review-repertoire
description: Check the name and ECO of every repertoire variation against the Lichess catalog and flag lines that stop mid-theory. Use when asked to review, audit or check the repertoire.
---

# Review the repertoire

This is read-only: report findings and do not edit `repertoire/` unless the user asks. A fix must
never change a `VariantId`.

1. **Names and ECO.** Run `uv run python -m catalog.validate`. It matches by final position, because
   catalog names repeat and lines transpose. Report each problem with the catalog's value.
2. **Lines that stop early.** With `app.book.loader.load_book`, list for each variation:
   - its length in plies;
   - whether the last move is the user's. If it is the bot's, the user's next move is not checked;
   - whether it is a prefix of another variation in the same repertoire. Then it ends where the other
     continues, which is fine only if the short line is meant to hand over to the engine.
3. **Coverage.** Use `catalog.loader` to list named catalog positions that continue from the
   repertoire's lines, as candidates. The catalog is not a book: it lists named positions, not
   recommended replies, so present these as options and do not add them.
4. **Report** a table per repertoire, most serious findings first. State what was not checked: this
   validates names and legality, not whether a line is good theory.
