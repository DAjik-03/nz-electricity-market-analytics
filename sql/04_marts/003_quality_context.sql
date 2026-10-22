-- These are the assessment retained at refresh time, not a claim that a new DQ
-- execution occurred. As-of date and source/denominator units remain visible.
CREATE VIEW analytics.mart_source_quality AS
SELECT c.*,q.as_of_date,q.status AS dq_run_status,r.refresh_id
FROM analytics.refresh_status r JOIN quality.dq_run q ON q.run_id=r.dq_run_id
JOIN quality.coverage_metric c ON c.run_id=q.run_id
WHERE (SELECT analytics.assert_current());

CREATE VIEW analytics.mart_quality_results AS
SELECT d.*,q.as_of_date,q.status AS dq_run_status,r.refresh_id
FROM analytics.refresh_status r JOIN quality.dq_run q ON q.run_id=r.dq_run_id
JOIN quality.rule_result d ON d.run_id=q.run_id
WHERE (SELECT analytics.assert_current());
