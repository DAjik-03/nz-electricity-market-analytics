-- Source-period eligibility is configuration, not a fabricated observed baseline.
-- Keep all ten original content baselines untouched for physical regressions.
CREATE TABLE quality.required_publication (
 source_name text NOT NULL CHECK(source_name IN ('prices','reconciliation','generation','nsp')),
 source_month date NOT NULL,
 PRIMARY KEY(source_name,source_month)
);
INSERT INTO quality.required_publication
 SELECT s, m::date FROM unnest(ARRAY['prices','reconciliation','generation']) s
 CROSS JOIN generate_series(date '2025-09-01',date '2026-08-01',interval '1 month') m;
INSERT INTO quality.required_publication VALUES ('nsp','2026-09-01');

UPDATE quality.rule SET query_sql=replace(query_sql,'quality.expected_publication','quality.required_publication')
 WHERE rule_code IN ('DQ01','DQ04');
UPDATE quality.rule SET rule_name='Required approved release publications',
 description='Compare selected source/month slots with the explicitly approved continuous twelve-month release.',
 expected_condition='All 37 required slots selected and loaded.',
 treatment='Restore the approved complete selection; never bridge an absent month.'
 WHERE rule_code='DQ01';

-- Retain the existing profiling algorithm; change only its expected calendar scope.
DO $$
DECLARE body text;
BEGIN
 SELECT pg_get_functiondef('quality.prepare_selected_profiles()'::regprocedure) INTO body;
 IF position('quality.expected_publication' IN body)=0 THEN
   RAISE EXCEPTION 'Expected prior calendar definition not found';
 END IF;
 EXECUTE replace(body,'quality.expected_publication','quality.required_publication');
END $$;
