# Career pack: NZ electricity market analytics

Use these statements for Data Analyst, BI Analyst, Insights Analyst and Reporting Analyst applications. They describe an independent portfolio project; do not present it as paid client work or a production deployment.

## One-line description

Built a SQL-led NZ electricity market analytics workflow and Power BI report to investigate wholesale price pressure, regional differences and the reliability of the underlying official data.

## CV bullets

- Built a PostgreSQL analytical warehouse from official Electricity Authority data, preserving source lineage and validating 71.8 million reconciled-volume rows with explicit DST and historical mapping controls.
- Investigated wholesale price pressure using SQL and month/hour comparisons, identifying regional pressure not captured by the National P99 indicator and distinguishing sustained price exposure from short-lived extremes.
- Delivered a five-page Power BI report with 59 DAX measures, event drill-through and visible data-quality coverage; reconciled report values and validated filters, bookmarks and save/reopen behaviour in Desktop.

For a short CV, use the second and third bullets. For a SQL-heavy role, retain the first. Avoid claiming commercial savings or user adoption: neither was measured.

## LinkedIn / portfolio description

An independent New Zealand electricity market analytics project built with PostgreSQL, SQL, Power BI and supporting Python ingestion. I combined official Electricity Authority prices, reconciled volumes, generation and network mappings for September 2025–August 2026, then developed quality controls and analytical marts before building the report.

The investigation distinguishes sustained March price exposure from August volatility and highlights regional pressure not captured by the National P99 indicator. Five Power BI pages connect market monitoring, demand and generation context, event investigation and data quality. The project preserves Unknown geography and source exceptions, uses fixed full-period thresholds and describes associations rather than causality. Source code, methods, validation evidence and genuine Desktop screenshots are available in the repository; this is a portfolio implementation, not a production deployment.

## 60-second interview explanation

“I wanted to understand how an analyst could monitor New Zealand wholesale electricity prices without losing regional detail or overlooking data limitations. I used official Electricity Authority data for a continuous twelve-month period, with PostgreSQL and SQL doing the main modelling and analysis and Python supporting ingestion.

“The difficult part was getting the meaning right: trading days can have 46 or 50 half-hours, network mappings change over time, and National and regional totals must stay separate. I built quality rules that preserve known exceptions rather than hiding them.

“The analysis showed that March had sustained price exposure while August had greater volatility, and that some regional pressure was absent from the National flag. I built a five-page Power BI report to investigate those patterns, reconciled its values and tested its interactions. I would describe the results as associations, not causes.”

## Approximately three-minute interview explanation

“The business question was how to monitor wholesale price pressure in New Zealand in a way that is useful for investigation. A monthly average is helpful, but it can hide short extreme events, differences between regions and gaps in source coverage. My aim was to make those distinctions visible in one traceable workflow.

“I started with four official Electricity Authority source families: prices, reconciled injection and offtake, generation, and network supply point mappings. I audited the actual files before finalising the model. The approved release covers September 2025 to August 2026, with 37 selected publications. Python handles versioned acquisition, hashes and parsing. PostgreSQL and SQL handle the warehouse, quality rules and analytical products.

“Several design choices mattered. Demand comes from Offtake rather than an invented separate raw source. Generation keeps its connection-level grain. Geography is mapped using historical validity, and unmapped records remain Unknown. I also used UTC interval identity with local trading dates because daylight-saving transition days do not have 48 periods. Three invalid historical mapping boundaries remain quarantined rather than silently corrected.

“The quality framework has 29 rules. The retained assessment is 21 passes, eight warnings and no failures. That does not mean perfect data: the warnings deliberately expose known mapping gaps, sparse generation and revision limitations. I kept evidence for repeatability and reconciled the analytical products against independently calculated results.

“For the analysis, I defined price pressure using each scope's full-period 99th percentile and grouped adjacent flagged half-hours into events. March had higher average exposure, while August had much higher volatility. Higher demand remained associated with pressure after comparing within local month and hour, but that does not control for every system condition. There were also 88 half-hours with regional pressure and no National flag, which is a strong reason to include a regional investigation path.

“The final Power BI report has five pages, moving from an Executive overview to regions, generation, selected events and data quality. It keeps the threshold fixed under date filters and separates selected-event values from National context. I checked the actual Desktop model, numerical results, bookmarks, drill-through and saved/reopened behaviour.

“What I would bring to an analyst role is that combination of SQL implementation, careful metric definition and clear communication. I can explain what the data show, how the result was validated and what cannot yet be concluded. The next investigation would need outage, reserve and forecast data; I would not infer those causes from price and generation patterns alone.”

## Technical deep-dive talking points

- **Grain before joins:** explain reconciliation participant/network/flow keys and why generation connection grain is necessary.
- **DST:** show the real 46/50-period validation, UTC identities, local offsets and fold handling.
- **Time-valid mappings:** distinguish pricing POC from NSP; explain invalid-boundary quarantine and historical Unknown records.
- **Versioned ingestion:** immutable bytes, manifest SHA-256, publication identity, idempotent loads and explicit revision selection.
- **KPI denominators:** weighted price is a pooled ratio; energy shares and mean interval shares are not interchangeable.
- **Quality and release gates:** known warnings remain visible; unexplained failures block release; repeat-run comparison excludes operational timestamps.
- **DAX scope:** separate National/Zone facts, disconnected fixed thresholds and full-event cards that survive interval selection.
- **Evidence:** 103 historical regression tests, 19 Desktop numerical checks and 16 row-count checks are different validation layers, not one combined test claim.

## Likely questions and concise answers

| Question | Answer |
|---|---|
| Why PostgreSQL rather than doing everything in Power BI? | SQL makes source grains, transformations, quality rules and analytical outputs inspectable before the reporting layer. Power BI then focuses on measures and interaction. |
| What was the hardest data issue? | Historical geography and trading intervals: mappings have validity boundaries, and DST days require 46 or 50 periods. I validated real rows and retained invalid source boundaries explicitly. |
| Did you prove demand caused higher prices? | No. A month/hour comparison reduced some timing differences, but weather, outages, available capacity and other confounders remain. The result is an association. |
| Does zero FAIL mean the data are complete? | No. Eight warnings retain known exceptions. Mapping coverage, sparse activity, revision finality and interval completeness are separate questions. |
| Why not recalculate P99 after filtering? | The approved report compares selected periods against one fixed historical benchmark. Recalculating it would change the definition of pressure with the slicer. |
| Can the model predict price spikes? | No. The percentile is retrospective and uses the full release. It supports description and investigation, not forecasting. |
| What changed because of the analysis? | It informed the report design: duration and peaks alongside averages, regional pressure alongside National monitoring, and coverage alongside findings. No external business impact was measured. |
| Why is generation not equal to demand? | Listed generation and reconciled Offtake have different source populations and definitions; I did not force an energy-balance identity. |
| What did Python do? | Acquisition, parsing, orchestration and validation support. SQL remains the main transformation and analytical layer. |
| Is this deployed? | It is a genuine, runtime-validated local Power BI Project. No production service or Power BI Service deployment is claimed. |
| What would you improve next? | Extend the period and align official outage, reserve, forecast and hydro context at interval grain, with clear source/version controls. |

## Claim sources

[Case study](portfolio_case_study.md), [full findings](findings.md), [release counts](release_validation.md), [quality framework](data_quality_framework.md) and [Desktop acceptance](desktop_acceptance.md) support these statements. Reuse the approved wording and limitations when adapting material for a vacancy.
