let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "SELECT refresh_id,input_fingerprint,dq_run_id,dq_as_of_date,dq_status,#(lf) is_current,status,completed_at AT TIME ZONE 'UTC' AS completed_at_utc,#(lf) input_manifest::text AS input_manifest#(lf)FROM analytics.refresh_status", null, [EnableFolding=false]) else error "Release gate failed"
in Rows
