# Analytical methods and validation

The analysis covers September 2025-August 2026 and supports the completed Power BI report. Findings are descriptive associations, not causal estimates.

`src/run_findings.py` executes named SELECT blocks from seven files under `sql/05_analysis/` in a single **REPEATABLE READ READ ONLY** transaction and rolls it back. PostgreSQL enforces read-only operation; no migrations, temporary/persistent tables, refresh, acquisition or load are invoked. The session disables parallel workers to avoid the previously observed shared-memory limit, with a bounded statement timeout. A current-release assertion precedes queries. Catalog metadata, full SQL-block hashes, output row counts/result hashes, selected publications, cache hash, thresholds, current refresh and migration metadata are recorded before/after in [query manifest](../outputs/analysis/query_manifest.json).

## Definitions and safeguards

| Area | Method / safeguard |
|---|---|
| Observation grain | Exactly one National or named Zone row per UTC half-hour; joins to Zone counts aggregate to interval before joining National. Never join participant-level facts directly for comparisons. |
| Threshold | Stored full-precision full-year P99, `weighted_price >= p99`; fixed retrospective threshold. Each Zone's percentile has its own population. |
| Weighted price | Sum price numerator / sum priced Offtake; monthly and event weighted values pool components. P95 and SD use equal interval weights. |
| Pressure timing | Interval-start local month/hour/weekday. Event count assigned by start month separately. Hours = interval count × half-hour, not a count of event records. |
| Contextual comparator | For each pressure half-hour, average non-pressure values in the same month and local hour. Average these comparator values across pressure intervals, thereby weighting strata by pressure exposure. No weekday/weather/outage controls. |
| Generation | Absolute mean MWh per half-hour and separately pooled shares. Renewable/fossil primary shares exclude Storage and Unclassified; other shares use listed output. No generation-Offtake balance calculation. |
| Sensitivity | Annual all-listed renewable range allocates all unclassified output first to non-renewable, then renewable, retaining the listed denominator. This tests direction within listed energy only; it is not a code mapping or a bound on unlisted generation. |
| Spread | Existing max-minus-min five-known-Zone weighted price, only when all expected Zones are represented. National, Zone-only and normal comparison counts are explicit. Some comparison rows overlap. |
| Cross-regional episode | Analysis-only union of known-Zone flagged intervals, grouped when consecutive UTC start equals previous end. Changing flagged Zone does not split an episode. A non-flagged half-hour does split it. No existing event table redefinition. |
| Event demand percentile | Annual National demand `cume_dist`, averaged across the event's constituent intervals. Not the percentile of an event-level average; includes tied ranks. |
| Case selection | Five deterministic contrast rules in `validate_findings.py`, with exact IDs and rationale saved. Context searched after these criteria surfaced candidate events. Cases are not used as a random sample. |

No confidence intervals, significance tests, regression or ML are needed for these descriptive population comparisons. Consecutive half-hours are dependent, the groups are selected by observed price, and the full-year threshold contains future information relative to any earlier date. No causal or forecast interpretation is justified.

## Independent recomputation

Final acceptance: **103 tests passed**, zero failures/errors/skips, in **978.012 seconds**. **11 independent analytical check groups passed**. The final 21 named SQL outputs include 20 outputs repeated from the initial run with identical result hashes, plus the added per-Zone spread comparison. All seven analytical view hashes equal the approved continuous-release refresh-38 hashes; the cache and 37 selected publications are unchanged across the full test run. All 24 applied migration checksums still match. See [executed evidence](../outputs/analysis/analysis_validation.json) for the exact checks and repeated query names.

`src/validate_findings.py` reads saved SQL extracts, including compressed National intervals and known-Zone flags. It uses Python's standard library to independently check:

- read-only state, approved fingerprint, 37 selections and every saved-result hash;
- full scope and unique grain, UTC continuity and actual 46/50-period DST days;
- monthly component-weighted prices, P95, population SD, demand, generation and renewable share;
- demand mean/median/P95 and the month/hour comparator;
- absolute generation, pooled shares, classification coverage and sensitivity bounds;
- deduplicated Zone overlap and reconstructed cross-regional episode boundaries;
- complete-only spread distributions;
- every event's duration, National context and demand-percentile definition.

[Analysis validation](../outputs/analysis/analysis_validation.json) records the executed checks. The [evidence register](../outputs/analysis/findings_evidence.csv) maps findings to named SQL blocks, exact observed results, comparison populations and qualifications. [Derived comparisons](../outputs/analysis/derived_comparisons.json) preserve independently calculated differences. Original SQL results retain precision; report values are rounded only for display.

The full regression suite was run because Python analysis utilities were added; its output is [analytical full test results](../outputs/analysis/full_test_results.json). It exercised existing rollback-only fixtures and can write test run metadata, but analytical queries cannot mutate warehouse/mart data. Current-release integrity and all final analytical queries were checked again after tests. No historical DQ execution was repeated merely to refresh documentation.

## External context verification

[External context register](../outputs/analysis/external_context.json) records publisher, URL, covered dates, publication date, section locator, relevant case, supported context and limitations. PDF internal covered dates control; index labels for several links referred to a different week's document. Those mismatched weeks were discarded for the selected cases.

EA context for August identifies availability and forecast issues; context for early March documents node-level constraints. These do not quantify the causal contribution to our weighted National/Zone metrics. The August report has inconsistent exact Huntly trip timing across sections, which is left unresolved rather than silently repaired. The reviewed late-March text does not establish the selected 03:30 case's cause. No source quote is used as a substitute for a saved analytical value.

## Interpretation checks

Review covered scope labels, pooled denominators, unchanged Unknown/Unclassified treatment, comparison-group overlap, ex-post P99 disclosure and restrained causal wording. The completed report passed Desktop runtime acceptance.

## Reproduction commands

From the project root with the existing database and ignored `.env`:

```text
.venv\Scripts\python.exe src/run_findings.py
.venv\Scripts\python.exe src/validate_findings.py
.venv\Scripts\python.exe src/write_findings.py
.venv\Scripts\python.exe src/run_all_tests.py --output outputs/analysis/full_test_results.json
git diff --check
```

The first command reads existing marts only. JSON gzip files use deterministic gzip metadata and contain no raw participant rows. CSV companions are bounded summary outputs. Do not run ingestion/warehouse load or analytical refresh as a prerequisite for this completed release.
