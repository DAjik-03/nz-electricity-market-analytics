-- Registered, inspectable SQL; changes after application require a new migration.

-- DQ01: Required pilot publications
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ01',
'Required pilot publications',
'Completeness',
'metadata.publication_selection',
'High',
'Compare selected source/month slots with the approved pilot configuration.',
'Missing source/months make comparisons incomplete.',
'All ten required slots selected and loaded.',
'Restore the intended selection; do not acquire extra history.',
true,
$query$SELECT quality.outcome(count(*),jsonb_build_object('missing_slots',coalesce(jsonb_agg(to_jsonb(e)),'[]')))
 FROM quality.expected_publication e LEFT JOIN metadata.publication_selection s USING(source_name,source_month)
 LEFT JOIN metadata.source_publication p USING(publication_id) WHERE p.publication_id IS NULL OR p.status<>'loaded'$query$);


-- DQ02: Staging publication counts
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ02',
'Staging publication counts',
'Completeness',
'staging.*',
'High',
'Compare all loaded publications with physical source row counts, including NSP and wide generation.',
'Truncated staging cannot support reproducible transformations.',
'Zero publication count discrepancies.',
'Investigate rollback/lineage; never adjust metadata to hide loss.',
true,
$query$WITH a AS (SELECT source,publication_id,sum(rows) rows FROM dq_stage GROUP BY 1,2)
 SELECT quality.outcome(count(*),coalesce(jsonb_agg(jsonb_build_object('publication',p.publication_id,'expected',p.staged_rows,'actual',a.rows)),'[]'))
 FROM metadata.source_publication p LEFT JOIN a USING(publication_id) WHERE p.status='loaded' AND p.staged_rows IS DISTINCT FROM a.rows$query$);


-- DQ03: Normalised fact populations
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ03',
'Normalised fact populations',
'Completeness',
'core.fact_*',
'High',
'Compare physical facts with stage-normalised counts, loaded metadata and original content baselines.',
'Missing or multiplied facts bias every downstream total.',
'Zero population discrepancies.',
'Inspect SQL unpivot/join loss and source version.',
true,
$query$WITH a AS (SELECT source,publication_id,sum(rows) rows FROM dq_population GROUP BY 1,2),
 b AS (SELECT publication_id,sum(normalised_rows) rows FROM dq_stage GROUP BY 1)
 SELECT quality.outcome(count(*),coalesce(jsonb_agg(jsonb_build_object('publication',p.publication_id,'core',a.rows,'stage',b.rows,'metadata',p.fact_rows)),'[]'))
 FROM metadata.source_publication p LEFT JOIN a USING(publication_id) LEFT JOIN b USING(publication_id)
 LEFT JOIN quality.expected_publication e ON e.source_name=p.source_name AND e.baseline_sha256=p.sha256
 WHERE p.status='loaded' AND p.source_name<>'nsp' AND
 (a.rows IS DISTINCT FROM b.rows OR a.rows IS DISTINCT FROM p.fact_rows OR (e.baseline_sha256 IS NOT NULL AND a.rows<>e.baseline_fact_rows))$query$);


-- DQ04: Dataset date/period completeness
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ04',
'Dataset date/period completeness',
'Completeness',
'selected fact populations',
'High',
'Require all expected date/periods at dataset level, not per participant or plant.',
'Dataset gaps undermine time comparisons.',
'All three fact sources cover every approved interval.',
'Investigate absent files/periods; never zero-fill sparse plants.',
true,
$query$WITH expected AS (SELECT p.source_name,p.publication_id,i.interval_id FROM metadata.publication_selection p
 JOIN quality.expected_publication e USING(source_name,source_month)
 JOIN quality.input_interval i ON date_trunc('month',i.trading_date)::date=p.source_month WHERE p.source_name<>'nsp'),
 missing AS (SELECT e.* FROM expected e LEFT JOIN dq_period f ON f.source=e.source_name AND f.publication_id=e.publication_id AND f.interval_id=e.interval_id WHERE f.interval_id IS NULL)
 SELECT quality.outcome(count(*),jsonb_build_object('missing_source_intervals',count(*))) FROM missing$query$);


-- DQ05: Generation structural padding
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ05',
'Generation structural padding',
'Validity',
'staging.generation_daily / generation fact',
'High',
'Nonexistent TP cells must remain null; real TP cells must exist and source TP must match the interval.',
'Padding misinterpreted as energy creates false activity.',
'Zero invalid padding or TP linkage rows.',
'Reject malformed source/transform; never create zero observations.',
true,
$query$WITH bad AS (
 SELECT s.publication_id FROM staging.generation_daily s CROSS JOIN LATERAL jsonb_each_text(to_jsonb(s)) v
 WHERE v.key ~ '^TP[0-9]+$' AND ((core.tp_start(s."Trading_Date"::date,substring(v.key from 3)::int) IS NULL)<>(v.value IS NULL))
 UNION ALL SELECT f.publication_id FROM quality.input_generation f LEFT JOIN quality.input_interval i USING(interval_id)
 WHERE i.trading_period IS DISTINCT FROM f.source_tp)
 SELECT quality.outcome(count(*),jsonb_build_object('invalid_cells_or_fact_rows',count(*))) FROM bad$query$);


-- DQ06: Price grain uniqueness
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ06',
'Price grain uniqueness',
'Uniqueness',
'quality.input_price',
'High',
'Check publication plus approved business key; measure excess rows rather than hide collisions.',
'Duplicate business keys double-count observations.',
'Zero excess duplicate rows.',
'Reject and investigate source or join; retain the approved grain.',
true,
$query$SELECT quality.outcome(coalesce(sum(n-1),0)::bigint,jsonb_build_object('duplicate_groups',count(*))) FROM (SELECT count(*) n FROM quality.input_price GROUP BY publication_id,interval_id,pricing_node_id HAVING count(*)>1) d$query$);


-- DQ07: Reconciled Volume grain uniqueness
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ07',
'Reconciled Volume grain uniqueness',
'Uniqueness',
'quality.input_volume',
'High',
'Check publication plus approved business key; measure excess rows rather than hide collisions.',
'Duplicate business keys double-count observations.',
'Zero excess duplicate rows.',
'Reject and investigate source or join; retain the approved grain.',
true,
$query$SELECT quality.outcome(coalesce(sum(n-1),0)::bigint,jsonb_build_object('duplicate_groups',count(*))) FROM (SELECT count(*) n FROM quality.input_volume GROUP BY publication_id,interval_id,connection_id,participant_id,flow_direction HAVING count(*)>1) d$query$);


-- DQ08: Generation grain uniqueness
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ08',
'Generation grain uniqueness',
'Uniqueness',
'quality.input_generation',
'High',
'Check publication plus approved business key; measure excess rows rather than hide collisions.',
'Duplicate business keys double-count observations.',
'Zero excess duplicate rows.',
'Reject and investigate source or join; retain the approved grain.',
true,
$query$SELECT quality.outcome(coalesce(sum(n-1),0)::bigint,jsonb_build_object('duplicate_groups',count(*))) FROM (SELECT count(*) n FROM quality.input_generation GROUP BY publication_id,interval_id,generator_id,connection_id HAVING count(*)>1) d$query$);


-- DQ09: Unique loaded selections
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ09',
'Unique loaded selections',
'Versioning',
'metadata.publication_selection',
'High',
'Only one correctly identified loaded publication may be selected per source/month.',
'Analysts must not see mixed or incomplete revisions.',
'Zero duplicate slots or unloaded/misaligned selections.',
'Select a successfully committed version transactionally.',
true,
$query$WITH bad AS (SELECT source_name FROM metadata.publication_selection GROUP BY source_name,source_month HAVING count(*)<>1
 UNION ALL SELECT s.source_name FROM metadata.publication_selection s LEFT JOIN metadata.source_publication p USING(publication_id)
 WHERE p.status IS DISTINCT FROM 'loaded' OR p.source_name IS DISTINCT FROM s.source_name OR p.source_month IS DISTINCT FROM s.source_month)
 SELECT quality.outcome(count(*),jsonb_build_object('bad_selections',count(*))) FROM bad$query$);


-- DQ10: Finite measures and flow domains
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ10',
'Finite measures and flow domains',
'Validity',
'source measures and fact measures',
'High',
'Check source parseability and finite required core measures; preserve finite negative values and separate flows.',
'Invalid values can poison sums or misclassify demand.',
'Zero invalid measures or flow labels.',
'Reject invalid input; negative finite values are not automatically invalid.',
true,
$query$WITH bad AS (
 SELECT publication_id FROM quality.input_price WHERE dollars_per_mwh IS NULL OR dollars_per_mwh::text IN ('NaN','Infinity','-Infinity')
 UNION ALL SELECT publication_id FROM quality.input_volume WHERE kilowatt_hours IS NULL OR kilowatt_hours::text IN ('NaN','Infinity','-Infinity') OR flow_direction IS NULL OR flow_direction NOT IN ('Offtake','Injection')
 UNION ALL SELECT publication_id FROM quality.input_generation WHERE kilowatt_hours IS NULL OR kilowatt_hours::text IN ('NaN','Infinity','-Infinity')
 UNION ALL SELECT publication_id FROM staging.final_energy_price WHERE quality.number("DollarsPerMegawattHour") IS NULL OR "DollarsPerMegawattHour" IN ('NaN','Infinity','-Infinity')
 UNION ALL SELECT publication_id FROM staging.reconciled_volume WHERE quality.number("KilowattHours") IS NULL OR "KilowattHours" IN ('NaN','Infinity','-Infinity')
 UNION ALL SELECT publication_id FROM staging.generation_daily s CROSS JOIN LATERAL jsonb_each_text(to_jsonb(s)) v
 WHERE v.key ~ '^TP[0-9]+$' AND v.value IS NOT NULL AND (quality.number(v.value) IS NULL OR v.value IN ('NaN','Infinity','-Infinity')))
 SELECT quality.outcome(count(*),jsonb_build_object('invalid_source_cells_or_facts',count(*))) FROM bad$query$);


-- DQ11: Independent NZ calendar and DST
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ11',
'Independent NZ calendar and DST',
'Validity',
'core.dim_trading_interval',
'High',
'Generate expected instants from Pacific/Auckland midnights and check all endpoint/offset/fold fields.',
'DST errors shift prices/energy or duplicate repeated local times.',
'46 on 2025-09-28; 50 on 2026-04-05; August 48; all intervals 30 minutes.',
'Stop temporal processing if any date-specific calendar mismatch occurs.',
true,
$query$WITH bad AS (SELECT i.interval_id FROM dq_expected_interval e FULL JOIN quality.input_interval i USING(trading_date,trading_period)
 WHERE e.start_utc IS DISTINCT FROM i.start_utc OR e.end_utc IS DISTINCT FROM i.end_utc
 OR i.local_start IS DISTINCT FROM (i.start_utc AT TIME ZONE 'Pacific/Auckland')
 OR i.local_end IS DISTINCT FROM (i.end_utc AT TIME ZONE 'Pacific/Auckland')
 OR i.utc_offset_minutes IS DISTINCT FROM (extract(epoch FROM ((i.start_utc AT TIME ZONE 'Pacific/Auckland')-(i.start_utc AT TIME ZONE 'UTC')))/60)::int
 OR i.end_utc_offset_minutes IS DISTINCT FROM (extract(epoch FROM ((i.end_utc AT TIME ZONE 'Pacific/Auckland')-(i.end_utc AT TIME ZONE 'UTC')))/60)::int
 OR i.is_dst IS DISTINCT FROM (i.utc_offset_minutes=780) OR i.end_is_dst IS DISTINCT FROM (i.end_utc_offset_minutes=780)
 OR i.fold IS DISTINCT FROM (((i.start_utc-interval '1 hour') AT TIME ZONE 'Pacific/Auckland')=i.local_start)::int
 OR i.end_fold IS DISTINCT FROM (((i.end_utc-interval '1 hour') AT TIME ZONE 'Pacific/Auckland')=i.local_end)::int
 OR i.timezone IS DISTINCT FROM 'Pacific/Auckland')
 SELECT quality.outcome(count(*),jsonb_build_object('calendar_rows', (SELECT count(*) FROM quality.input_interval),
 'spring_periods',(SELECT count(*) FROM quality.input_interval WHERE trading_date='2025-09-28'),
 'fall_periods',(SELECT count(*) FROM quality.input_interval WHERE trading_date='2026-04-05'))) FROM bad$query$);


-- DQ12: Publication month alignment
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ12',
'Publication month alignment',
'Validity',
'facts / source publication',
'High',
'Fact interval month and declared source identity must agree.',
'Month comparisons must represent the declared publication.',
'Zero rows outside their source month or source type.',
'Investigate file identity/selection; do not move rows to fit.',
true,
$query$SELECT quality.outcome(coalesce(sum(f.rows),0)::bigint,jsonb_build_object('bad_interval_groups',count(*)))
 FROM dq_period f LEFT JOIN quality.input_interval i USING(interval_id) LEFT JOIN metadata.source_publication p USING(publication_id)
 WHERE p.source_name IS DISTINCT FROM f.source OR p.source_month IS DISTINCT FROM date_trunc('month',i.trading_date)::date$query$);


-- DQ13: Required fact and source references
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ13',
'Required fact and source references',
'Referential Integrity',
'all physical facts',
'High',
'Check publication, interval, source-row and required dimension references. Nullable unresolved NSP keys are excluded here.',
'Missing references lose facts in joins.',
'Zero orphan facts.',
'Reject broken lineage/dimensions; Unknown is allowed separately.',
true,
$query$WITH bad AS (
 SELECT f.publication_id FROM quality.input_price f LEFT JOIN metadata.source_publication p USING(publication_id)
 LEFT JOIN quality.input_interval i USING(interval_id) LEFT JOIN core.dim_pricing_node d USING(pricing_node_id)
 LEFT JOIN staging.final_energy_price s USING(publication_id,source_row_number)
 WHERE p.publication_id IS NULL OR i.interval_id IS NULL OR d.pricing_node_id IS NULL OR s.source_row_number IS NULL
 UNION ALL SELECT f.publication_id FROM quality.input_volume f LEFT JOIN metadata.source_publication p USING(publication_id)
 LEFT JOIN quality.input_interval i USING(interval_id) LEFT JOIN core.dim_connection d USING(connection_id)
 LEFT JOIN core.dim_participant a USING(participant_id) LEFT JOIN staging.reconciled_volume s USING(publication_id,source_row_number)
 WHERE p.publication_id IS NULL OR i.interval_id IS NULL OR d.connection_id IS NULL OR a.participant_id IS NULL OR s.source_row_number IS NULL
 UNION ALL SELECT f.publication_id FROM quality.input_generation f LEFT JOIN metadata.source_publication p USING(publication_id)
 LEFT JOIN quality.input_interval i USING(interval_id) LEFT JOIN core.dim_connection d USING(connection_id)
 LEFT JOIN core.dim_generator g USING(generator_id) LEFT JOIN staging.generation_daily s USING(publication_id,source_row_number)
 WHERE p.publication_id IS NULL OR i.interval_id IS NULL OR d.connection_id IS NULL OR g.generator_id IS NULL OR s.source_row_number IS NULL)
 SELECT quality.outcome(count(*),jsonb_build_object('orphan_facts',count(*))) FROM bad$query$);


-- DQ14: NSP mapping identity and effective validity
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ14',
'NSP mapping identity and effective validity',
'Referential Integrity',
'volume/generation NSP lineage',
'High',
'Mapped keys must belong to the declared NSP snapshot, connection and valid effective interval; unresolved states retain no resolved key.',
'Wrong mappings bias regional totals and historical attribution.',
'Zero false resolved or invalid mapping references.',
'Preserve unresolved facts; reject fabricated matches.',
true,
$query$SELECT quality.outcome(coalesce(sum(f.rows),0)::bigint,jsonb_build_object('invalid_mapping_groups',count(*)))
 FROM dq_mapping f LEFT JOIN quality.input_nsp n ON n.nsp_version_id=f.nsp_version_id AND n.publication_id=f.nsp_snapshot_publication_id
 LEFT JOIN metadata.source_publication p ON p.publication_id=f.nsp_snapshot_publication_id
 LEFT JOIN quality.input_interval i USING(interval_id)
 WHERE p.source_name IS DISTINCT FROM 'nsp' OR p.status IS DISTINCT FROM 'loaded'
 OR f.mapping_status NOT IN ('mapped','unmapped','ambiguous') OR f.mapping_status IS NULL
 OR ((f.mapping_status='mapped') IS DISTINCT FROM (f.nsp_version_id IS NOT NULL))
 OR (f.nsp_version_id IS NOT NULL AND (n.nsp_version_id IS NULL OR n.connection_id<>f.connection_id
 OR n.boundary_status='invalid_boundary' OR i.start_utc<n.valid_from_utc OR (n.boundary_status='valid_bounded' AND i.start_utc>=n.valid_to_utc_exclusive)))$query$);


-- DQ15: Price numeric reconciliation
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ15',
'Price numeric reconciliation',
'Consistency',
'staging / core native totals',
'High',
'Compare exact staging/core native sums by publication and flow, then original-content totals with the approved baseline.',
'Energy/price transformations must preserve source measures.',
'Exact stage/core agreement; Phase 1 price tolerance 1e-8, energy tolerance zero.',
'Investigate unit, rounding, lineage or transform loss; these sums are not business KPIs.',
true,
$query$WITH paired AS (SELECT coalesce(a.publication_id,b.publication_id) pid,a.total actual,b.total expected
 FROM (SELECT * FROM dq_population WHERE source='prices') a FULL JOIN (SELECT * FROM dq_stage WHERE source='prices') b USING(publication_id,flow)
 WHERE a.total IS DISTINCT FROM b.total), baseline AS (
 SELECT a.publication_id pid,sum(a.total) actual,e.baseline_total expected FROM dq_population a
 JOIN metadata.source_publication p USING(publication_id) JOIN quality.expected_publication e ON e.source_name=p.source_name AND e.baseline_sha256=p.sha256
 WHERE a.source='prices' GROUP BY a.publication_id,e.baseline_total,e.tolerance HAVING abs(sum(a.total)-e.baseline_total)>e.tolerance)
 SELECT quality.outcome(count(*),coalesce(jsonb_agg(to_jsonb(x)),'[]')) FROM (SELECT * FROM paired UNION ALL SELECT * FROM baseline) x$query$);


-- DQ16: Offtake and Injection reconciliation
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ16',
'Offtake and Injection reconciliation',
'Consistency',
'staging / core native totals',
'High',
'Compare exact staging/core native sums by publication and flow, then original-content totals with the approved baseline.',
'Energy/price transformations must preserve source measures.',
'Exact stage/core agreement; Phase 1 price tolerance 1e-8, energy tolerance zero.',
'Investigate unit, rounding, lineage or transform loss; these sums are not business KPIs.',
true,
$query$WITH paired AS (SELECT coalesce(a.publication_id,b.publication_id) pid,a.total actual,b.total expected
 FROM (SELECT * FROM dq_population WHERE source='reconciliation') a FULL JOIN (SELECT * FROM dq_stage WHERE source='reconciliation') b USING(publication_id,flow)
 WHERE a.total IS DISTINCT FROM b.total), baseline AS (
 SELECT a.publication_id pid,sum(a.total) actual,e.baseline_total expected FROM dq_population a
 JOIN metadata.source_publication p USING(publication_id) JOIN quality.expected_publication e ON e.source_name=p.source_name AND e.baseline_sha256=p.sha256
 WHERE a.source='reconciliation' GROUP BY a.publication_id,e.baseline_total,e.tolerance HAVING abs(sum(a.total)-e.baseline_total)>e.tolerance)
 SELECT quality.outcome(count(*),coalesce(jsonb_agg(to_jsonb(x)),'[]')) FROM (SELECT * FROM paired UNION ALL SELECT * FROM baseline) x$query$);


-- DQ17: Generation energy reconciliation
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ17',
'Generation energy reconciliation',
'Consistency',
'staging / core native totals',
'High',
'Compare exact staging/core native sums by publication and flow, then original-content totals with the approved baseline.',
'Energy/price transformations must preserve source measures.',
'Exact stage/core agreement; Phase 1 price tolerance 1e-8, energy tolerance zero.',
'Investigate unit, rounding, lineage or transform loss; these sums are not business KPIs.',
true,
$query$WITH paired AS (SELECT coalesce(a.publication_id,b.publication_id) pid,a.total actual,b.total expected
 FROM (SELECT * FROM dq_population WHERE source='generation') a FULL JOIN (SELECT * FROM dq_stage WHERE source='generation') b USING(publication_id,flow)
 WHERE a.total IS DISTINCT FROM b.total), baseline AS (
 SELECT a.publication_id pid,sum(a.total) actual,e.baseline_total expected FROM dq_population a
 JOIN metadata.source_publication p USING(publication_id) JOIN quality.expected_publication e ON e.source_name=p.source_name AND e.baseline_sha256=p.sha256
 WHERE a.source='generation' GROUP BY a.publication_id,e.baseline_total,e.tolerance HAVING abs(sum(a.total)-e.baseline_total)>e.tolerance)
 SELECT quality.outcome(count(*),coalesce(jsonb_agg(to_jsonb(x)),'[]')) FROM (SELECT * FROM paired UNION ALL SELECT * FROM baseline) x$query$);


-- DQ18: NSP boundary semantics and lineage
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ18',
'NSP boundary semantics and lineage',
'Validity',
'core.dim_nsp_version',
'High',
'Retain original fields and distinguish valid bounded, genuinely open and invalid histories.',
'Invalid null endpoints must never become open histories.',
'Zero changed source fields or inconsistent derived semantics.',
'Preserve evidence; never clamp impossible trading periods.',
true,
$query$SELECT quality.outcome(count(*),jsonb_build_object('bad_boundary_records',count(*))) FROM quality.input_nsp n
 LEFT JOIN staging.network_supply_point s USING(publication_id,source_row_number)
 WHERE n.original_start_date IS DISTINCT FROM s."Start date" OR n.original_start_tp IS DISTINCT FROM s."Start TP"
 OR n.original_end_date IS DISTINCT FROM s."End date" OR n.original_end_tp IS DISTINCT FROM s."End TP"
 OR (n.boundary_status='invalid_boundary' AND (n.valid_from_utc IS NOT NULL OR n.valid_to_utc_exclusive IS NOT NULL OR n.exception_reason IS NULL))
 OR (n.boundary_status='valid_open' AND (n.original_end_date IS NOT NULL OR n.original_end_tp IS NOT NULL OR n.valid_from_utc IS NULL))
 OR (n.boundary_status='valid_bounded' AND (n.valid_from_utc IS NULL OR n.valid_to_utc_exclusive IS NULL OR n.valid_to_utc_exclusive<=n.valid_from_utc))
 OR (n.boundary_status<>'invalid_boundary' AND (n.valid_from_utc IS DISTINCT FROM core.tp_start(n.original_start_date::date,n.original_start_tp::int)
 OR n.valid_to_utc_exclusive IS DISTINCT FROM core.tp_start(n.original_end_date::date,n.original_end_tp::int)+interval '30 minutes'))
 OR n.boundary_status NOT IN ('valid_bounded','valid_open','invalid_boundary')$query$);


-- DQ19: Historical NSP quarantine register
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ19',
'Historical NSP quarantine register',
'Validity',
'NSP invalid/open histories',
'High',
'Report invalid/open populations and verify the three known invalid records remain unchanged in the approved snapshot.',
'Transparent exceptions prevent false claims of complete temporal certainty.',
'WARN for preserved exceptions; FAIL if a known exception disappears or changes.',
'Seek authoritative clarification; preserve originals.',
true,
$query$WITH known(nsp,ended,tp) AS (VALUES ('KFA0111VMOLEN','2014-09-28','48'),('KNA0011KIPTEN','2014-09-28','48'),('WQG0011DMFLEN','2018-09-30','48')),
 missing AS (SELECT k.* FROM known k WHERE NOT EXISTS (SELECT 1 FROM quality.input_nsp n JOIN metadata.source_publication p USING(publication_id)
 JOIN quality.expected_publication e ON e.source_name='nsp' AND e.baseline_sha256=p.sha256
 WHERE n.nsp=k.nsp AND n.original_end_date=k.ended AND n.original_end_tp=k.tp AND n.boundary_status='invalid_boundary')),
 counts AS (SELECT boundary_status,count(*) n FROM quality.input_nsp GROUP BY 1)
 SELECT quality.outcome(CASE WHEN (SELECT count(*) FROM missing)>0 THEN (SELECT count(*) FROM missing) ELSE (SELECT count(*) FROM quality.input_nsp WHERE boundary_status='invalid_boundary') END,
 jsonb_build_object('statuses',(SELECT jsonb_agg(to_jsonb(c)) FROM counts c),'exceptions',(SELECT jsonb_agg(jsonb_build_object('nsp',nsp,'end_date',original_end_date,'end_tp',original_end_tp,'reason',exception_reason)) FROM quality.input_nsp WHERE boundary_status='invalid_boundary')),
 NOT EXISTS(SELECT 1 FROM missing))$query$);


-- DQ20: NSP overlaps and gaps
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ20',
'NSP overlaps and gaps',
'Consistency',
'valid NSP histories',
'High',
'Compare successive valid ranges per snapshot and NSP; a gap is diagnostic, overlap blocks.',
'Overlapping histories can multiply effective joins.',
'Zero overlaps; report gaps without inventing continuity.',
'Investigate overlaps; retain source gaps as warnings.',
true,
$query$WITH x AS (SELECT count(*) FILTER (WHERE next_start IS NOT NULL AND (valid_to_utc_exclusive IS NULL OR valid_to_utc_exclusive>next_start)) overlaps,
 count(*) FILTER (WHERE valid_to_utc_exclusive<next_start) gaps FROM dq_nsp_edges)
 SELECT quality.outcome(CASE WHEN overlaps>0 THEN overlaps ELSE gaps END,to_jsonb(x),overlaps=0) FROM x$query$);


-- DQ21: Facts intersecting invalid histories
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ21',
'Facts intersecting invalid histories',
'Validity',
'fact / original NSP ordinal boundaries',
'High',
'Check source date/TP ordinal ranges without inventing UTC for invalid endpoints, and prohibit mapped invalid histories.',
'Using impossible boundaries creates unsupported historical attribution.',
'Zero intersecting or invalid-mapped fact rows.',
'Quarantine affected processing for authoritative review.',
true,
$query$SELECT quality.outcome(coalesce(sum(f.rows),0)::bigint,jsonb_build_object('invalid_intersection_groups',count(*)))
 FROM dq_mapping f JOIN quality.input_interval i USING(interval_id)
 WHERE EXISTS (SELECT 1 FROM quality.input_nsp n WHERE n.boundary_status='invalid_boundary'
 AND n.publication_id=f.nsp_snapshot_publication_id AND (n.nsp_version_id=f.nsp_version_id OR
 (n.connection_id=f.connection_id AND (to_char(i.trading_date,'YYYYMMDD')::bigint*100+i.trading_period)
 BETWEEN (to_char(n.original_start_date::date,'YYYYMMDD')::bigint*100+n.original_start_tp::int)
 AND (to_char(n.original_end_date::date,'YYYYMMDD')::bigint*100+n.original_end_tp::int))))$query$);


-- DQ22: Effective ambiguity and historical HWA guard
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ22',
'Effective ambiguity and historical HWA guard',
'Consistency',
'selected volume / generation mapping',
'High',
'Recompute effective candidate counts at distinct connection/interval/snapshot keys; guard pre-August HWA/KIWI non-mapping.',
'Regional attribution must reflect actual effective evidence.',
'WARN for correctly unresolved ambiguity; FAIL for status/candidate inconsistency or retrospective HWA mapping.',
'Do not pick arbitrary NSPs or backfill a later relationship.',
true,
$query$WITH observed AS MATERIALIZED (SELECT DISTINCT interval_id,connection_id,nsp_snapshot_publication_id FROM dq_mapping),
 candidates AS (SELECT o.interval_id,o.connection_id,o.nsp_snapshot_publication_id,count(n.nsp_version_id) n
 FROM observed o JOIN quality.input_interval i USING(interval_id) LEFT JOIN quality.input_nsp n
 ON n.connection_id=o.connection_id AND n.publication_id=o.nsp_snapshot_publication_id AND n.boundary_status<>'invalid_boundary'
 AND i.start_utc>=n.valid_from_utc AND (n.boundary_status='valid_open' OR i.start_utc<n.valid_to_utc_exclusive) GROUP BY 1,2,3),
 x AS (SELECT coalesce(sum(f.rows) FILTER (WHERE f.mapping_status IS DISTINCT FROM CASE a.n WHEN 0 THEN 'unmapped' WHEN 1 THEN 'mapped' ELSE 'ambiguous' END
 OR (c.poc IN ('HWA1101','HWA1102') AND c.network='KIWI' AND i.trading_date<'2026-08-01' AND f.mapping_status<>'unmapped')),0)::bigint bad,
 coalesce(sum(f.rows) FILTER (WHERE a.n>1),0)::bigint ambiguous,
 coalesce(sum(f.rows) FILTER (WHERE c.poc IN ('HWA1101','HWA1102') AND c.network='KIWI' AND i.trading_date<'2026-08-01'),0)::bigint historical_hwa_rows
 FROM dq_mapping f JOIN candidates a USING(interval_id,connection_id,nsp_snapshot_publication_id)
 JOIN core.dim_connection c USING(connection_id) JOIN quality.input_interval i USING(interval_id))
 SELECT quality.outcome(CASE WHEN bad>0 THEN bad ELSE ambiguous END,to_jsonb(x),bad=0) FROM x$query$);


-- DQ23: Price Zone diagnostic coverage
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ23',
'Price Zone diagnostic coverage',
'Completeness',
'selected monthly coverage',
'Medium',
'Measure known/Unknown using row denominator for prices and native kWh for energy; no universal coverage threshold.',
'Regional comparisons can be biased by changing coverage.',
'Preserve Unknown; WARN where coverage is incomplete, with month-specific denominators.',
'Keep national totals; qualify regional analysis.',
false,
$query$SELECT quality.outcome((SELECT count(*) FROM dq_coverage WHERE source_name='prices' AND (unknown_value<>0 OR total_value=0)),
 coalesce(jsonb_agg(to_jsonb(c)||jsonb_build_object('coverage_pct',100*known_value/nullif(total_value,0)) ORDER BY source_month),'[]'),true,
 jsonb_build_object('affected_unit','source-months','denominator_policy','native signed kWh for energy; rows for prices; null coverage when total is zero'))
 FROM dq_coverage c WHERE source_name='prices'$query$);


-- DQ24: Offtake Zone energy coverage
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ24',
'Offtake Zone energy coverage',
'Completeness',
'selected monthly coverage',
'Medium',
'Measure known/Unknown using row denominator for prices and native kWh for energy; no universal coverage threshold.',
'Regional comparisons can be biased by changing coverage.',
'Preserve Unknown; WARN where coverage is incomplete, with month-specific denominators.',
'Keep national totals; qualify regional analysis.',
false,
$query$SELECT quality.outcome((SELECT count(*) FROM dq_coverage WHERE source_name='reconciliation_offtake' AND (unknown_value<>0 OR total_value=0)),
 coalesce(jsonb_agg(to_jsonb(c)||jsonb_build_object('coverage_pct',100*known_value/nullif(total_value,0)) ORDER BY source_month),'[]'),true,
 jsonb_build_object('affected_unit','source-months','denominator_policy','native signed kWh for energy; rows for prices; null coverage when total is zero'))
 FROM dq_coverage c WHERE source_name='reconciliation_offtake'$query$);


-- DQ25: Generation Zone energy coverage
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ25',
'Generation Zone energy coverage',
'Completeness',
'selected monthly coverage',
'Medium',
'Measure known/Unknown using row denominator for prices and native kWh for energy; no universal coverage threshold.',
'Regional comparisons can be biased by changing coverage.',
'Preserve Unknown; WARN where coverage is incomplete, with month-specific denominators.',
'Keep national totals; qualify regional analysis.',
false,
$query$SELECT quality.outcome((SELECT count(*) FROM dq_coverage WHERE source_name='generation' AND (unknown_value<>0 OR total_value=0)),
 coalesce(jsonb_agg(to_jsonb(c)||jsonb_build_object('coverage_pct',100*known_value/nullif(total_value,0)) ORDER BY source_month),'[]'),true,
 jsonb_build_object('affected_unit','source-months','denominator_policy','native signed kWh for energy; rows for prices; null coverage when total is zero'))
 FROM dq_coverage c WHERE source_name='generation'$query$);


-- DQ26: Sparse and zero generation series
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ26',
'Sparse and zero generation series',
'Completeness',
'generator / connection / month observations',
'Medium',
'Report fewer observed dates than month length, all-zero series and first/last observed edges.',
'Sparse operations can be mistaken for ingestion loss.',
'Informational WARN; do not assume absent activity is missing data.',
'Do not zero-fill or fail dataset eligibility; investigate with plant context.',
false,
$query$SELECT quality.outcome(count(*) FILTER (WHERE observed_days<expected_days OR all_zero),
 jsonb_build_object('series',count(*),'short_series',count(*) FILTER (WHERE observed_days<expected_days),
 'all_zero_series',count(*) FILTER (WHERE all_zero),'diagnostics',coalesce(jsonb_agg(to_jsonb(s) ORDER BY source_month,gen_code,poc,network) FILTER (WHERE observed_days<expected_days OR all_zero),'[]')),true,
 jsonb_build_object('affected_unit','series-months','edges','first/last are observed boundaries, not plant commissioning dates')) FROM dq_series s$query$);


-- DQ27: Reconciliation I/X flag disagreement
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ27',
'Reconciliation I/X flag disagreement',
'Consistency',
'measured flow / NSP I-X metadata',
'Medium',
'Injection expects I flow=1 and Offtake expects X flow=1; report original rows, aggregated matches and kWh separately by month.',
'Metadata disagreement limits interpretation, not the validity of measured totals.',
'WARN until authoritative semantics are clarified.',
'Never delete, invert or repair the measured energy from these flags.',
false,
$query$WITH bad AS (SELECT f.*,p.source_month FROM dq_mapping f JOIN metadata.source_publication p USING(publication_id)
 JOIN quality.input_nsp n ON n.nsp_version_id=f.nsp_version_id AND n.publication_id=f.nsp_snapshot_publication_id
 WHERE f.source='reconciliation' AND CASE f.flow WHEN 'Injection' THEN n.source_metadata->>'I flow' ELSE n.source_metadata->>'X flow' END IS DISTINCT FROM '1'),
 monthly AS (SELECT source_month,sum(rows) affected_source_rows,count(*) affected_aggregates,sum(kwh) affected_kwh FROM bad GROUP BY 1)
 SELECT quality.outcome(coalesce(sum(affected_source_rows),0)::bigint,coalesce(jsonb_agg(to_jsonb(m) ORDER BY source_month),'[]'),true) FROM monthly m$query$);


-- DQ28: Historical pilot freshness and finality
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ28',
'Historical pilot freshness and finality',
'Timeliness',
'selected source periods / retrieval metadata',
'Medium',
'Report age from latest source month end as of an explicit date, retrieval time and revision eligibility separately from availability.',
'Users must not confuse historical coverage with current-market freshness.',
'Historical age is informational; loaded reconciliation is not certified final.',
'Refresh only under an approved source-version workflow; no SLA inferred for this pilot.',
false,
$query$WITH x AS (SELECT s.source_name,max(s.source_month) latest_source_month,max(p.downloaded_at) latest_selected_retrieval,
 current_setting('quality.as_of_date')::date-(max(s.source_month)+interval '1 month'-interval '1 day')::date days_since_latest_period,
 count(*) selected_publications,bool_and(p.status='loaded') selected_available,
 CASE WHEN s.source_name='reconciliation' THEN 'revision-eligible; finality not certified' ELSE 'observed publication; finality not inferred' END finality
 FROM metadata.publication_selection s JOIN metadata.source_publication p USING(publication_id) GROUP BY 1)
 SELECT quality.outcome(count(*) FILTER (WHERE source_name='reconciliation' OR days_since_latest_period>0),
 coalesce(jsonb_agg(to_jsonb(x) ORDER BY source_name),'[]'),true,jsonb_build_object('affected_unit','sources','as_of_date',current_setting('quality.as_of_date'),'availability_scope','selected local publications only; no live publisher discovery')) FROM x$query$);


-- DQ29: Selected views and retained versions
INSERT INTO quality.rule(rule_code,rule_name,quality_dimension,target_object,severity,description,business_implication,expected_condition,treatment,is_blocking,query_sql)
VALUES ('DQ29',
'Selected views and retained versions',
'Versioning',
'selected views / retained publication lineage',
'High',
'Compare selected-view populations with selected physical versions, and require original and previously audited publications to survive.',
'Summing multiple revisions inflates results and destroys auditability.',
'Zero selected-view overcounts or removed prior publications.',
'Switch selection transactionally; retain physical predecessors.',
true,
$query$WITH exposed AS (SELECT 'prices'::text source,publication_id,count(*) rows FROM core.v_selected_price GROUP BY 2
 UNION ALL SELECT 'reconciliation',publication_id,count(*) FROM core.v_selected_reconciled_volume GROUP BY 2
 UNION ALL SELECT 'generation',publication_id,count(*) FROM core.v_selected_generation GROUP BY 2),
 expected AS (SELECT a.source,a.publication_id,sum(a.rows) rows FROM dq_population a JOIN metadata.publication_selection s USING(publication_id) GROUP BY 1,2),
 bad AS (SELECT coalesce(a.publication_id,b.publication_id) pid FROM exposed a FULL JOIN expected b USING(source,publication_id) WHERE a.rows IS DISTINCT FROM b.rows
 UNION ALL SELECT -1 FROM quality.expected_publication e WHERE NOT EXISTS (SELECT 1 FROM metadata.source_publication p WHERE p.source_name=e.source_name AND p.sha256=e.baseline_sha256 AND p.status='loaded')
 UNION ALL SELECT -1 FROM (SELECT DISTINCT v->>'sha256' sha,v->>'source_name' source FROM quality.dq_run q CROSS JOIN LATERAL jsonb_array_elements(q.input_manifest->'publications') v WHERE q.status IN ('COMPLETED','BLOCKED')) old
 WHERE NOT EXISTS(SELECT 1 FROM metadata.source_publication p WHERE p.source_name=old.source AND p.sha256=old.sha))
 SELECT quality.outcome(count(*),jsonb_build_object('view_or_retention_discrepancies',count(*),'official_publications',(SELECT count(*) FROM metadata.source_publication))) FROM bad$query$);
