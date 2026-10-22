SELECT refresh_id,input_fingerprint,dq_run_id,dq_as_of_date,dq_status,
 is_current,status,completed_at AT TIME ZONE 'UTC' AS completed_at_utc,
 input_manifest::text AS input_manifest
FROM analytics.refresh_status;
