# Validated historical release

The accepted release spans 1 September 2025 to 31 August 2026: 365 local dates, 17,520 UTC half-hour intervals and 37 selected publication slots. Twelve each cover price, reconciled volume and generation; one NSP snapshot supplies effective mapping history.

| Fact | Rows |
|---|---:|
| Price | 4,276,595 |
| Reconciled volume | 71,843,944 |
| Generation connection | 1,652,118 |

December prices use 31 official final daily files because the monthly publication was incomplete. The aggregate contains 361,584 unique rows; 349,920 overlapping monthly rows matched with no price conflicts. The incomplete monthly diagnostic is not selected. [Source decision](december_source_decision.md)

Real 46-period spring and 50-period fall DST source rows were validated against Pacific/Auckland intervals. Natural keys showed no collisions across the pilot; generation connection grain remains necessary. Effective mapping preserves Unknown rather than backfilling later NSP/network validity.

## Gate status

Source/DST, Unknown coverage, eligible-month criteria and grain checks passed within assessed scope (PRE01/03/04/05). PRE02 remains partly unresolved: three historical NSP records have invalid DST-date end trading periods. Original values stay preserved and quarantined; facts do not intersect invalid boundaries. Valid-history gaps, sparse/all-zero generation, flow-flag disagreement and revision eligibility remain documented limitations.

The retained DQ run has 29 rules: 21 PASS, eight WARN and zero FAIL. Repeat substantive results matched. Analytical refresh 38 uses this selected release and DQ run 5. All 103 regression tests passed in the recorded validation, not rerun for export. [Test evidence](../outputs/analysis/full_test_results.json) | [Quality framework](data_quality_framework.md)

[Source manifest](../outputs/scale_up/source_manifest.json) and [candidate validation](../outputs/scale_up/candidate_validation.json) retain source hashes and native reconciliation evidence. These are technical population checks, not certification of final settlement or complete plant activity.
