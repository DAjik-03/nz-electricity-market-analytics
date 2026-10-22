let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "SELECT classification_version,fuel_code,tech_code,standard_category,#(lf) generation_role,energy_status,evidence_url,review_status,rationale#(lf)FROM analytics.ref_generation_classification WHERE classification_version=1", null, [EnableFolding=false]) else error "Release gate failed"
in Rows
