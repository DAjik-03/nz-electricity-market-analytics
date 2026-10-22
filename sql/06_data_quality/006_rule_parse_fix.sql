-- OVERLAPS is a PostgreSQL keyword; use an unambiguous diagnostic field.
UPDATE quality.rule SET query_sql=replace(query_sql,'overlaps','overlap_count') WHERE rule_code='DQ20';
