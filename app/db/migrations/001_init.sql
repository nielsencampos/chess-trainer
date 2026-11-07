-- The book. openings/*.json is the source; any line is playable with either color.

CREATE TABLE repertoires (
    repertoire_id VARCHAR PRIMARY KEY,
    source VARCHAR NOT NULL,  -- 'repo' (openings/) or 'user' (imported, never reloaded)
    file_path VARCHAR,
    file_hash VARCHAR,
    loaded_at TIMESTAMPTZ NOT NULL
);

-- Rows are never deleted: a line that disappears becomes inactive, because statistics are
-- keyed on variant_id.
CREATE TABLE variants (
    variant_id VARCHAR PRIMARY KEY,
    repertoire_id VARCHAR NOT NULL,
    eco VARCHAR,
    opening VARCHAR,
    pgn VARCHAR NOT NULL,
    moves_san VARCHAR[] NOT NULL,
    final_epd VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE names (
    entity_type VARCHAR NOT NULL,
    entity_id VARCHAR NOT NULL,
    locale VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    PRIMARY KEY (entity_type, entity_id, locale)
);

CREATE TABLE book_moves (
    repertoire_id VARCHAR NOT NULL,
    variant_id VARCHAR NOT NULL,
    epd_before VARCHAR NOT NULL,
    ply INTEGER NOT NULL,
    uci VARCHAR NOT NULL,
    san VARCHAR NOT NULL
);

-- Reference only: names positions and validates openings/. The bot does not play from it.
CREATE TABLE catalog_loads (
    content_hash VARCHAR NOT NULL,
    source_commit VARCHAR NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE openings_catalog (
    eco VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    pgn VARCHAR NOT NULL,
    epd VARCHAR NOT NULL,
    source_commit VARCHAR NOT NULL
);
