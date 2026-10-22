# Data quality framework

## continuous-release release scope

Expanded DQ runs 4 and 5 completed as-of 2026-10-01 with identical substantive results: 21 PASS / 8 WARN / 0 FAIL and zero blocking failures. The new `quality.required_publication` configuration declares the 36 monthly fact slots for September 2025–August 2026 plus the pinned NSP snapshot. DQ01 and DQ04 and the calendar profile use this explicit scope. `quality.expected_publication` retains its original ten hash/count/total baselines unchanged; it is no longer overloaded as the full release calendar. Native staging/core reconciliation and retained-version checks still cover every physical publication.

The 29 rule identities are preserved. The measured full-year result happens to have the same 21/8/0 status counts as the original pilot; affected counts and 36 monthly coverage records are newly assessed. Prior results and 34 analytical/DQ exports remain archived under outputs/scale_up/pilot_archive with zero hash mismatches. December final-price packaging has explicit child lineage, without changing price grain or weakening incomplete-file rejection. See [continuous-release validation](release_validation.md).

The following sections describe the original framework; future changes are additive checksum-checked migrations.

The implemented framework applies SQL quality controls to the selected release; marts and Power BI consume its retained assessment.

## Objects and execution

The existing reserved `sql/06_data_quality/` directory is used consistently; folders 04_marts and 05_analysis contain the later analytical layers. Checksum-checked migrations run in filename order, following verified warehouse migrations. No existing core, staging or metadata definition is changed. The existing migration ledger records the additive quality scripts.

`quality.rule` registers 29 substantive rules with dimension, severity, target, description, expected condition, treatment, business implication, blocking flag and inspectable SQL. `quality.dq_run` records executions, explicit as-of date, start/end, code SHA-256, Git reference, input lineage/population fingerprint and operational status. `quality.rule_result` retains one result per rule/run, including a rule-definition snapshot so history is not silently relabelled. `quality.coverage_metric` stores month/source denominators and known/Unknown values. `quality.expected_publication` pins approved source/month slots and original warehouse content baselines; it does not forbid later revisions.

Read `quality.v_latest_dq_results`, `quality.v_latest_dq_summary` and `quality.v_latest_coverage` for the latest completed assessment. These views include a completed blocking assessment rather than hiding it behind an earlier pass. An execution error is recorded separately in `quality.dq_run`; always inspect its latest row too. An interrupted RUNNING execution is not a successful assessment. No arbitrary weighted quality score exists.

Temporary SQL profiles aggregate counts, native sums, interval presence, connection/interval mappings and observed generation series once per run. They are dropped on commit/rollback and are not analytical marts. Physical input views are thin projections of warehouse tables; selected input views project warehouse selected-version views. They enable isolated rollback-only corruption fixtures without weakening core constraints.

The runner uses the existing warehouse advisory lock and a REPEATABLE READ transaction. Publication selection, aggregates and rule results therefore share one database snapshot under the supported single-writer workflow. The RUNNING record is created first; profiles/results/coverage and completed status commit together. SQL exceptions roll back partial results and mark the run ERROR. A completed rule failure produces BLOCKED if its rule is blocking, while known limitations remain WARN. External writers that ignore the lock are outside this development workflow, but the snapshot remains consistent.

The fingerprint covers publication metadata, selected versions and physical native count/total profiles. Code SHA-256 covers quality SQL and runner files; the Git reference can be the parent commit during development. This is an inspectable lineage/population fingerprint, not a cryptographic hash of every warehouse row. Statuses/metrics are deterministic for the same data, rule code and as-of date; run IDs, clock times and elapsed durations are intentionally different.

## Rule interpretation

- Completeness is evaluated at dataset/date/TP level. A plant need not appear on every date. Sparse/zero series and first/last observation edges are diagnostics; no missing dates are zero-filled.
- Uniqueness checks use publication plus approved business grain. Required FKs are checked independently from permissible unresolved geography.
- Native totals reconcile stage to core exactly and original bytes to the approved baseline. The only baseline tolerance is 1e-8 for the ingestion floating-point price sum; kWh is exact. These sums are reconciliation controls, not market metrics.
- The calendar is independently generated from Pacific/Auckland local midnights, validating actual 46/48/50 dates, endpoint offsets, folds and duration. Source TP padding must remain null.
- NSP source boundaries remain unchanged. Three impossible historical ends warn; mapped use or source-ordinal intersection blocks. Original date/TP ordinal comparisons detect an intersection without inventing UTC for an invalid endpoint. Valid history overlaps block; source gaps warn and remain gaps.
- Effective mapping identity is checked across physical revisions. Ambiguity/HWA and coverage diagnostics use selected populations. No arbitrary candidate is selected and later validity is never backfilled.
- Price geography is measured only: unanimous non-null Zone across all effective candidates, otherwise Unknown. It does not establish an additive price-to-NSP bridge or change core pricing identity. Its denominator is price rows, never price sums. Offtake/generation denominators are native signed kWh, matching approved ingestion controls. A zero denominator yields null coverage, never 100%; negative/cancelling populations would require interpretation rather than a universal threshold.
- I/X disagreement preserves both original-row counts and connection/interval/flow aggregate counts and kWh. It does not change measured flow or signs.
- Freshness uses monthly period end, or actual NSP snapshot date, against a recorded as-of date. Selected local availability, historical age and revision finality are separate. Loaded reconciliation remains revision-eligible; no publisher-finality certification is inferred and no historical-age SLA is invented.
- Original and previously audited publications must remain; selected-view counts must equal only selected physical populations. Synthetic revision and corruption fixtures are implementation evidence, not observed EMI revisions.

`affected_rows` is the number of failed observations/groups for the rule: it is explicitly labelled where the unit is source-months, cells, series-months, keys or publications. It must not be summed across rules as a unique count of bad source records. Severity describes potential impact; blocking applies only to FAIL, so a blocking-capable rule may legitimately WARN on a known exception.

## Reproduce

Activate the existing Python environment and start the existing PostgreSQL volume. Raw sources and warehouse facts do not need to be reloaded for DQ.

```text
docker compose up -d --wait
python src/run_data_quality.py init
python src/run_data_quality.py run --as-of 2026-09-21
python src/check_data_quality_determinism.py
python -m unittest discover -s tests/quality -v
python src/export_data_quality_review.py
```

Omitting `--as-of` uses the current Auckland date. Determinism reruns reuse the preceding successful assessment's as-of date. `init` verifies applied hashes; changed migrations fail rather than silently altering prior logic. Inspect `outputs/data_quality/latest_summary.json`, per-run JSON, `determinism.json` and the registered SQL. Operational logs are ignored. Errors are recorded in the database and do not overwrite a last-successful export as if the failed run completed.

On a fresh clone follow the warehouse/raw restore instructions first. Preserve the PostgreSQL named volume; no destructive teardown is required. The optional notebook `notebooks/data_quality_review.ipynb` contains read-only queries for registered rules, current outcomes, coverage and run history.

## Scope and limitations

Only the approved non-contiguous pilot months are assessed. Local source availability does not prove live publisher completeness; sparse activity does not prove missing energy; raw source finality is unknown. PRE02 needs authoritative historical clarification. Mapping coverage varies, I/X semantics remain unresolved, and remapping to a new NSP snapshot requires a separate approved release policy. Owner privileges are local development privileges, not production governance. No automatic source repair, notification automation or next-phase analysis is introduced.

## Recovery verification — 22 September 2026

The preserved implementation uses `quality.rule` and `quality.rule_result` (the requested dq_rule/dq_result concepts), plus `quality.dq_run`; no table rename or migration rewrite was needed. Completed runs 2 and 3, as-of 2026-09-21, remain identical. Run 1 remains ERROR with zero persisted result rows. All 18 applied warehouse/quality migration hashes match local files. Recovery reuses these assessments without executing a new large DQ run; therefore freshness remains explicitly dated 2026-09-21.
