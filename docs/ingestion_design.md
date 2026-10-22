# Configurable ingestion design

The validated release uses immutable source versions, SHA-256 manifests, strict parsers and explicit publication selection. Reconciliation revisions replace a selected version; they are never added as extra analytical volume. December prices retain daily-constituent lineage. See [reproduction](reproducibility.md) and [release validation](release_validation.md).

## Configuration and discovery

`config/project_config.yml` supplies explicit completed historical months, the four official listing URLs, the NSP snapshot filename and project-relative storage locations. Reconciliation discovery visits only the requested years; other listing pages are inspected without downloading their archive. A hard upper bound of three months prevents accidental historical scale-up. `config/source_schema.json` fixes the four source-audit header contracts (4/9/57/27 columns).

Discovery rejects filenames or listing rows marked incomplete, including `_I` variants; unknown filename patterns are also rejected and reported. Recognised candidates are filtered by exact source/month. Reconciliation preparation timestamps in filenames select the newest listed publication for each month. Availability does not assert completeness or finality. A missing candidate stops acquisition. Listing hashes, retrieval time, selected URLs and rejected files are recorded in `outputs/pilot/discovery.json`.

## Immutable acquisition and versions

`src/ingestion/acquisition.py` stores publisher bytes at `data/raw/<source>/<sha256>/<filename>`. Downloads are written to a temporary file before publication. Existing content is hash-checked, never overwritten. The manifest identifies a publication by source, filename and SHA-256. It keeps original download time, HTTP Last-Modified, ETag, resolved URL, listing text, source month, unzoned preparation time and snapshot date. These are distinct metadata fields: neither a filename timestamp nor Last-Modified is asserted to be the exact publication instant.

`acquire --refresh` fetches the ten selected payloads again to detect changed bytes under unchanged URLs. This trades bandwidth for reliable detection, rather than trusting an unchanged filename or HTTP timestamp. Same bytes retain the same version and original metadata. A newly observed publication is retained alongside older versions. New selections are promoted together only after all downloads succeed; an interrupted run keeps successful immutable downloads and prior selections. Selection means **acquired**, not validated for analytics. Only a successful validation report establishes eligibility.

Run one writer per project. Concurrent manifest updates are not supported. Network/schema errors fail explicitly rather than retry indefinitely. Operational status and exceptions are written to ignored `outputs/pilot/run_state.json` and `pilot.log`; an interrupted `running` state is a signal to re-run/check, not a success claim. Acquisition can resume without losing older versions. Raw backups are still required: Git does not contain raw files, and EMI may replace an old publication.

`restore` fetches only missing pinned files and rejects changed publisher bytes. It never upgrades a version. Existing files must pass hashes. The original source-audit manifest remains separate and unchanged; the pilot compares its four shared filenames/checksums to that baseline.

## Parsers and staging

`parsers.py` rejects missing/added/duplicate headers; column reordering is explicitly reported. IDs remain strings/categories and only empty CSV fields become null. Required fields, finite numeric measures, integral periods, exact dates, requested-month membership and natural-key uniqueness are checked. Unknown flow values fail. Negative measures are reported, not silently clipped.

Prices and reconciliation stay at source grain. Generation TP1–TP50 is melted, retaining only periods valid for each date. Structural padding must be null; a null within a valid interval fails. Original fuel, technology, POC, network and generator labels are retained. No missing participant/plant activity is synthesised as zero.

`intervals.py` steps in UTC from one Auckland midnight to the next. Every interval stores UTC start/end, local start/end with offsets, start/end offset minutes, DST flags and folds, and the named timezone. Fact staging carries the UTC start key plus original date/TP; the full date-specific calendar is a separate file. This avoids repeating twelve time attributes across millions of volume rows. All boundaries are half-open in UTC.

Derived CSV gzip files live in ignored `data/interim/pilot/<code-and-runtime-hash>/...`; their manifest references raw version IDs, output SHA-256, row counts, parser code and runtime versions. Per-file integrity sidecars prevent reuse of changed outputs. A successful cache hit verifies raw and derived bytes and does not rewrite them. Missing derived files are rebuilt; corrupt files fail rather than being silently accepted. If interruption occurs between publishing a derived file and its sidecar, inspect and remove only that reproducible derived file before retrying; never delete raw evidence to fix a derived-output problem.

The controlled pilot loads one fact/month into memory, with prices retained for join validation. It is not a benchmarked full-archive streaming architecture. No database dependency or warehouse DDL exists.

## Effective NSP mappings

Match price by POC and volume/generation by POC plus network, then filter inclusive original start/end date+TP. Do not filter historical records by Current flag. Source identity and snapshot lineage remain separate from price-node identity.

Valid source boundaries also receive derived `[start_utc, end_utc_exclusive)` values, based on the end of the stated final TP. Actual adjacent history records support this interpretation, including intraday changes. Three invalid historical end TPs cannot be converted and retain `boundary_valid=false`, original dates/TPs and source positions. They are not open-ended records. Any pilot observation intersecting one fails mapping. Full-history boundary policy remains an open review item.

For multiple effective matches, a geographic attribute is usable only when every matched value agrees and is non-null. Otherwise it is `Unknown`. Zone, Island and Network Reporting Region are assessed independently. Coverage measures distinguish no NSP match, multiple matches and missing/ambiguous geography, with original row weights and energy shares. No guessed geography, nearest-node or name-based mapping is permitted. The current staging files stay source-aligned; mapping diagnostics do not create warehouse dimensions.

## Reconciliation revisions

Exactly one acquired publication is selected per month. Revisions replace that selected month for analysis; they are never appended to old facts. `revisions.py` validates keys and compares inserted, removed, changed-measure and unchanged keys and signed kWh totals when more than one content version has been observed. Source-version IDs preserve lineage independently of business grain. No fabricated revision is created from a changed HTTP modification timestamp.

EMI says reconciliation may change for up to 14 months after first publication. All three pilot months remain labelled revision-eligible, without claiming a final revision number. Exact as-known historical reconstruction requires archived publications that may no longer be on the current listing. [Official source notes](https://www.emi.ea.govt.nz/Wholesale/Datasets/Volumes/Reconciliation).

## Complete eligible month rule

A month is **eligible for this versioned pilot**, not certified economically final, when recognised non-incomplete files exist for every fact, schemas/keys pass, all expected date/TP pairs occur at dataset level, every present row belongs to the actual 46/48/50-period calendar, reconciliation clock labels agree, and price nodes have no interior interval gaps between their first and last observation. Partial price-node edges are reported and not backfilled.

These independent dimensions remain visible:

| Dimension | Acceptance/reporting |
|---|---|
| File availability | Exact source/month; no explicit incomplete flag |
| Date/TP coverage | Complete dataset calendar; valid present rows; price interior continuity |
| Sparse activity | Participant/plant gaps and partial edges reported; not invented zeros or automatic file rejection |
| Revision finality | Separate revision-eligible status, not inferred from calendar coverage |
| Mapping | Unknown coverage retained and disclosed, not an eligibility veto |

This rule cannot prove every economically expected plant/participant is present without an authoritative active-population register. The three selected months are non-contiguous; they do not establish a continuous 2024–2026 analysis period.
