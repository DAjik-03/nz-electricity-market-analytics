-- Packaging is lineage metadata, never a new price business grain.
CREATE VIEW metadata.v_source_packaging AS
SELECT p.publication_id,p.source_name,p.source_month,p.filename,p.sha256,
 coalesce(p.manifest_metadata->>'source_form',
          CASE WHEN p.source_name='nsp' THEN 'official_snapshot' ELSE 'official_monthly' END) source_form,
 p.manifest_metadata->>'constituent_identity' constituent_identity,
 CASE WHEN p.manifest_metadata->>'source_form'='official_daily_aggregate'
      THEN jsonb_array_length(p.manifest_metadata->'constituents') ELSE 1 END constituent_count
FROM metadata.source_publication p;

CREATE VIEW metadata.v_source_constituent AS
SELECT p.publication_id,c.value->>'filename' filename,c.value->>'source_url' source_url,
 (c.value->>'trading_date')::date trading_date,c.value->>'sha256' sha256,
 (c.value->>'downloaded_at_utc')::timestamptz downloaded_at,
 c.value->>'http_last_modified' http_last_modified,c.value->>'etag' etag,
 c.value->>'price_status' price_status,c.value AS source_metadata
FROM metadata.source_publication p
CROSS JOIN LATERAL jsonb_array_elements(p.manifest_metadata->'constituents') c
WHERE p.manifest_metadata->>'source_form'='official_daily_aggregate';
