-- Stockfish's evaluation of every book position, from evals/book.json (made by
-- app.book.evaluate_book). From White's side, keyed by EPD so transpositions share a row.
-- Rows are replaced from the file when it changes and never deleted, like the book.

CREATE TABLE book_evals (
    epd VARCHAR PRIMARY KEY,
    cp INTEGER,
    mate INTEGER,
    best VARCHAR,
    depth INTEGER NOT NULL
);

CREATE TABLE book_eval_loads (
    content_hash VARCHAR NOT NULL,
    engine VARCHAR,
    positions INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL
);
