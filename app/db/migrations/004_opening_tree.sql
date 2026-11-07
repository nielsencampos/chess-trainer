-- The tree of the book: group > opening > subgroup > line. A NULL order means "Others".
ALTER TABLE repertoires ADD COLUMN group_key VARCHAR DEFAULT 'others';
ALTER TABLE repertoires ADD COLUMN sort_order INTEGER;
ALTER TABLE variants ADD COLUMN subgroup_json VARCHAR;
