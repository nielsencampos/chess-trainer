-- One row per game, rewritten on every move, so a game can continue after the app closes.
-- The PGN is the record of the game; the columns below it exist to filter and to resume.
CREATE TABLE games (
    game_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,  -- 'active' or 'finished'
    started_at TIMESTAMP NOT NULL,  -- UTC
    ended_at TIMESTAMP,  -- UTC
    user_color VARCHAR NOT NULL,
    time_control VARCHAR NOT NULL,
    level VARCHAR NOT NULL,
    pace VARCHAR NOT NULL,
    variant_ids VARCHAR[] NOT NULL,
    current_variant_id VARCHAR NOT NULL,
    result VARCHAR,
    termination VARCHAR,
    in_theory BOOLEAN NOT NULL,
    theory_until_ply INTEGER NOT NULL,
    moves_json VARCHAR NOT NULL,
    deviations_json VARCHAR NOT NULL,
    user_clock_ms BIGINT,
    bot_clock_ms BIGINT,
    ui_json VARCHAR NOT NULL,
    pgn VARCHAR NOT NULL,
    eco VARCHAR,
    opening VARCHAR,
    app_version VARCHAR NOT NULL,
    engine_name VARCHAR NOT NULL
);
