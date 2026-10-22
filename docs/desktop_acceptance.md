# Power BI Desktop acceptance

The genuine native PBIP passed runtime acceptance in Store Power BI Desktop 2.159.883.0 x64. This record summarises observed results, not expectations from a build specification.

| Gate | Observed result |
|---|---|
| Model | 16 loaded tables, four connection-only expressions, eight active single-direction relationships, 59 measures |
| Reconciliation | 19 numerical checks and all 16 table row counts passed |
| Release | Refresh 38, DQ run 5 and approved release fingerprint matched |
| Controls | E1-E5 presets, Reset, timeline, drill-through/Back and full-event card context passed |
| E3 | CNI 362.38 versus National 186.05; zero National flagged half-hours |
| Fixed P99 | March and August date filters changed visible data while National P99 remained 227.84 |
| Layout | All five pages rendered cleanly at approximately 98% scale |
| Persistence | Neutral All/Reset/Executive state saved, Desktop fully closed, same project reopened without stale drill-through filter |
| Reopen checks | Full-release values, E3, fixed P99, release/DQ and fingerprint passed |

Full-release weighted price is 67.876898672406518 and National P99 is 227.84134669510667. There are 68 National events, 176 flagged half-hours, 88 pressure hours, 264 any-Zone half-hours, 108 cross-regional episodes, 88 Zone-only half-hours and 104 all-five-Zone half-hours. DQ is 21 PASS / 8 WARN / 0 FAIL.

A previously persisted drill-through selection conflicted with a preset. Clearing the selection restored correct behaviour; the model/DAX was not changed. Clear an intentional drill-through selection before choosing a different event preset.

Microsoft TmdlSerializer parsed 16 tables, four expressions, eight relationships, 59 measures and 163 columns. The final static check validated 136 available-schema documents and references across all 137 documents. Desktop-emitted visualContainer 2.14 had a public schema endpoint returning HTTP 404. This is a public static-schema availability limitation, not a runtime failure; the emitted definition is preserved.

Six native contract tests passed independently of the historical 103-test regression suite. [Public screenshots](powerbi_gallery.md), [static evidence](../outputs/powerbi/native_static_validation.json) and [model specification](powerbi_model_spec.md) provide the review trail. Private runtime screenshots and recovery history are intentionally not part of this export.
