-- Locale codes carry their region (#32): en is en-US and es is es-419. The book's names are
-- renamed, not deleted; the next book sync writes them again from openings/ under the new codes.
UPDATE names SET locale = 'en-US' WHERE locale = 'en';
UPDATE names SET locale = 'es-419' WHERE locale = 'es';
UPDATE variants
SET subgroup_json = replace(replace(subgroup_json, '"en":', '"en-US":'), '"es":', '"es-419":')
WHERE subgroup_json IS NOT NULL;
