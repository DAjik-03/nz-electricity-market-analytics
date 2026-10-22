# December 2025 daily-final source decision

Audited 27 September 2026. All 31 official daily Final Energy Prices files are final (no `_I`). Each passes the exact four-column schema, stated date, Auckland calendar TP population and unique date/TP/POC key checks. The union has all 1,488 expected date/TP pairs and no collisions.

| Comparison | Rows/keys |
|---|---:|
| Daily-final union | 361,584 |
| Incomplete monthly diagnostic | 349,920 |
| Overlapping keys | 349,920 |
| Exact Decimal price conflicts | 0 |
| Daily-only keys | 11,664 |
| Monthly-only keys | 0 |

All daily-only keys occur on 31 December: 48 trading periods and 243 POCs. Neither population has an exclusive POC identity across the full month. Exact POC and date/TP difference lists are retained in `outputs/scale_up/december/audit.json`. The incomplete monthly publication is diagnostic-only and never eligible.

## Explicit lineage and revision identity

December source form is `official_daily_aggregate`; other months use `official_monthly`. The derived manifest embeds all 31 original filenames, URLs, trading dates, SHA-256 hashes, retrieval/HTTP metadata and final status. Original bytes remain immutable under ignored `data/raw`.

Identity is SHA-256 of canonical date-sorted constituent filename/URL/date/content-hash/status records. Retrieval timestamps are retained but excluded from identity. Canonical sorted CSV is compressed with mtime=0 and a gzip member name containing that identity. Thus changed constituent bytes create a new artifact SHA even when semantic prices remain identical. Unchanged inputs reconstruct byte-identically. The short external filename avoids Windows path-length limits; the SHA directory and full member identity preserve version uniqueness.

The existing gzip-capable warehouse loader receives the same price columns and business grain: trading interval + pricing POC. Its publication manifest_metadata retains all child lineage and source form. No special December fact or analytical grain is introduced. The validated release uses this deterministic source aggregate.

## Reproduction and validation

`python src/audit_december_daily_final.py --offline` verifies retained hashes and reconstructs without network access. `--refresh` explicitly observes publisher revisions while preserving old bytes. Eight acceptance gates pass, including deterministic bytes and explicit lineage.

`python -m unittest discover -s tests -v`: 46 tests passed, zero failures/errors, 1.809s. This includes 36 original source/pilot regressions and ten daily-final tests, including exact conflict detection, schema/date/key/calendar rejection, DST lengths, reconstruction and constituent revision identity. Historical modules are separate from the unchanged pilot ingestion code so its recorded fingerprint remains valid.

All 36 monthly slots and the NSP snapshot are selected in the validated release. The exact filenames and URLs are retained in outputs/scale_up/source_manifest.json. See [release validation](release_validation.md).