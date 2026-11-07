-- Games can also come from a PGN file. Those keep the PGN's own result, such as 1-0, in `result`,
-- because the app does not know which side was the user.
ALTER TABLE games ADD COLUMN source VARCHAR DEFAULT 'app';
ALTER TABLE games ADD COLUMN white VARCHAR;
ALTER TABLE games ADD COLUMN black VARCHAR;
ALTER TABLE games ADD COLUMN content_hash VARCHAR;
