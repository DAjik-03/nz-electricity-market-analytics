-- Isolated view inputs support rollback-only double-count fixtures without
-- touching the warehouse selected views or weakening any core constraint.
CREATE VIEW quality.input_selected_price AS SELECT * FROM core.v_selected_price;
CREATE VIEW quality.input_selected_volume AS SELECT * FROM core.v_selected_reconciled_volume;
CREATE VIEW quality.input_selected_generation AS SELECT * FROM core.v_selected_generation;
UPDATE quality.rule SET query_sql=replace(replace(replace(query_sql,
 'core.v_selected_price','quality.input_selected_price'),
 'core.v_selected_reconciled_volume','quality.input_selected_volume'),
 'core.v_selected_generation','quality.input_selected_generation') WHERE rule_code='DQ29';

-- NSP is a snapshot, not a month-long fact. Freshness uses its actual snapshot
-- date; monthly fact sources use period end. No age threshold means failure.
UPDATE quality.rule SET query_sql=$query$
 WITH x AS (SELECT s.source_name,max(s.source_month) latest_source_month,
 max(CASE WHEN s.source_name='nsp' THEN p.snapshot_date ELSE (s.source_month+interval '1 month'-interval '1 day')::date END) latest_source_period_end,
 max(p.downloaded_at) latest_selected_retrieval,
 current_setting('quality.as_of_date')::date-max(CASE WHEN s.source_name='nsp' THEN p.snapshot_date ELSE (s.source_month+interval '1 month'-interval '1 day')::date END) days_since_latest_period,
 count(*) selected_publications,bool_and(p.status='loaded') selected_available,
 CASE WHEN s.source_name='reconciliation' THEN 'revision-eligible; finality not certified' ELSE 'observed publication; finality not inferred' END finality
 FROM metadata.publication_selection s JOIN metadata.source_publication p USING(publication_id) GROUP BY 1)
 SELECT quality.outcome(count(*) FILTER (WHERE source_name='reconciliation' OR days_since_latest_period>0),
 coalesce(jsonb_agg(to_jsonb(x) ORDER BY source_name),'[]'),true,jsonb_build_object('affected_unit','sources',
 'as_of_date',current_setting('quality.as_of_date'),'availability_scope','selected local publications only; no live publisher discovery')) FROM x
 $query$ WHERE rule_code='DQ28';
