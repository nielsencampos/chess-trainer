-- Bot deviation (brief §6): the setup the game was started with and the bot's deviation, as
-- {"setup": {"from_move", "chance"} | null, "deviation": {"ply", "played_san", "expected_san"} | null}.
-- NULL for games saved before this migration and for imported games: the bot never deviated.
ALTER TABLE games ADD COLUMN bot_deviation_json VARCHAR;
