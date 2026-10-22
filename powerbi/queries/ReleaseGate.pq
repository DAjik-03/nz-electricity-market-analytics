let
    T = Value.NativeQuery(Source, "SELECT refresh_id,input_fingerprint,dq_run_id,is_current,status FROM analytics.refresh_status", null, [EnableFolding=false]),
    R = if Table.RowCount(T)=1 then T{0} else error "Expected exactly one approved release",
    Valid = R[refresh_id]=38 and R[dq_run_id]=5 and R[is_current]=true and R[status]="COMPLETED" and R[input_fingerprint]="b87ef82066c5bcd7055d350da94b28811467c3e0c2687489fb8363c5cd6e2cf6"
in if Valid then true else error "Release differs from approved Phase 5. Investigate; do not refresh/promote warehouse."
