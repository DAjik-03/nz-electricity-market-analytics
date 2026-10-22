# NZ wholesale price pressure: conditions to monitor

## Executive Summary

- **Monitor persistent pressure and isolated extremes separately.** September and March account for **63.6%** of National flagged half-hours, while August contains the largest observed spike. Monthly average price alone would miss this distinction. [F1, F2]
- **Demand and generation mix are useful context, not sufficient explanations.** Pressure-period demand remains **6.75% higher** after comparing the same month and local hour; renewable primary share is **89.05% versus 91.98%** in that comparator. Some pressure nevertheless occurs at low demand. [F4, F5, F7]
- **National monitoring needs a regional drill-through.** **88 half-hours** have Zone pressure without National pressure. Regional spreads are much wider during pressure, but spread alone does not prove a transmission constraint. [F3, F6]
- **Use coverage and official event context alongside indicators.** Keep Unknown geography, unclassified generation and revision status visible. The selected cases support investigation priorities, not causal, investment or policy recommendations. [F7]

## Reading the measures

The approved release covers **1 September 2025–31 August 2026**, with **17,520 National half-hours**. Prices are **NZD/MWh**, weighted by priced reconciled Offtake. Demand means Offtake, including Unknown geography nationally. A National pressure interval has weighted price at or above the stored full-precision P99 **227.84134669510667**; each Zone has its own threshold. An event is contiguous flagged UTC half-hours within one scope. These are retrospective, project-defined thresholds, not official scarcity or compliance classifications. Approximately one percent flagged per scope is a consequence of the full-period percentile definition, not a prospective risk estimate. [F1–F3]

Primary renewable/fossil shares use only classified primary generation as denominator. Storage and Unclassified are shown separately against all listed generation. Listed output is not gross national generation and is not an energy-balance identity with Offtake. Equal-interval statistics and energy-weighted prices answer different questions. [F5; [metric dictionary](kpi_dictionary.md)]

## 1. Monthly conditions: highest average and greatest volatility differ [F1]

March's weighted price was **152.38**, compared with **3.66 in January**, a difference of **148.71 NZD/MWh**. August's average was **82.30**, but its interval price SD was **167.53**, compared with March's **52.09**. Thus higher typical exposure and larger occasional extremes were different monitoring problems in this period.

| Month | Weighted price | P95 | Price SD | Demand GWh | Peak MW | Listed generation GWh | Renewable primary % | Flagged half-hours |
|---|---|---|---|---|---|---|---|---|
| 2025-09 | 118.42 | 216.06 | 80.06 | 3,593.80 | 6,610 | 3,529.74 | 89.86 | 49 |
| 2025-10 | 33.72 | 168.41 | 68.05 | 3,526.79 | 6,074 | 3,455.48 | 97.18 | 9 |
| 2025-11 | 67.02 | 153.67 | 57.50 | 3,374.93 | 5,694 | 3,300.93 | 96.70 | 5 |
| 2025-12 | 13.76 | 60.86 | 34.83 | 3,349.64 | 5,789 | 3,284.40 | 97.29 | 7 |
| 2026-01 | 3.66 | 13.79 | 9.91 | 3,267.91 | 5,417 | 3,205.10 | 97.21 | 0 |
| 2026-02 | 48.79 | 119.65 | 43.19 | 3,027.00 | 5,621 | 2,954.83 | 96.15 | 0 |
| 2026-03 | 152.38 | 222.72 | 52.09 | 3,428.01 | 5,668 | 3,364.71 | 91.41 | 63 |
| 2026-04 | 104.19 | 192.53 | 61.76 | 3,327.93 | 6,273 | 3,260.32 | 90.90 | 19 |
| 2026-05 | 80.99 | 132.26 | 48.13 | 3,613.07 | 6,373 | 3,570.44 | 91.49 | 5 |
| 2026-06 | 41.68 | 93.42 | 36.11 | 3,618.67 | 6,761 | 3,579.00 | 93.07 | 2 |
| 2026-07 | 60.45 | 123.12 | 82.19 | 3,968.75 | 7,303 | 3,968.86 | 95.74 | 7 |
| 2026-08 | 82.30 | 136.05 | 167.53 | 3,950.90 | 7,565 | 3,932.43 | 96.10 | 10 |

Prices, P95 and SD are NZD/MWh. This is **within-period monthly variation**, not established seasonal behaviour. Monthly demand totals also differ with calendar length; compare peak/interval demand for intensity. [Full monthly components, including fossil/storage/unclassified shares and spread](../outputs/analysis/monthly_overview.csv) preserve every requested overview metric. For analysts, show monthly exposure alongside tail and volatility measures rather than a single best/worst ranking.

## 2. Pressure clusters in months and hours, with different event lengths [F2]

There were **68 National events**, comprising **176 flagged half-hours** and **88 hours**. **28 events** were isolated half-hours; median duration was **1.0 hour**, P95 duration **3.5 hours**, and the longest **5.0 hours**. Median event peak price was **260.13** and P95 event peak **1,288.60 NZD/MWh**. Peak-price distribution is across events, not across all intervals. [Distribution](../outputs/analysis/national_event_distribution.json)

March contributed **63** flagged half-hours and September **49**, together **63.6%** of the total. Their within-month flag rates were **4.23%** and **3.41%**; January and February had no National flags. At local **07:00–07:59**, **26 of 730** half-hours were flagged (**3.56%**), versus **17 of 730 (2.33%)** at **18:00–18:59**. Weekday and weekend rates were **1.21%** and **0.50%**, respectively. These cuts are descriptive and correlated with month and demand, not independent risk factors. [Month](../outputs/analysis/pressure_by_month.csv), [hour](../outputs/analysis/pressure_by_hour.csv), [day type](../outputs/analysis/pressure_by_day_type.csv)

The monitoring implication is to retain both duration and peak: a long moderately high episode can matter differently from a single extreme half-hour. Use interval counts/rates for timing; [event starts by month](../outputs/analysis/event_starts_by_month.csv) assign an event to its start month and must not substitute for interval exposure.

## 3. Regional flags overlap substantially, but the National P99 indicator does not capture some local pressure [F3]

| Scope | P99 NZD/MWh | Events | Flagged hours | Median / max event hours | Peak NZD/MWh |
|---|---|---|---|---|---|
| National | 227.84 | 68 | 88 | 1.0 / 5.0 | 3,924.45 |
| CNI | 224.52 | 73 | 88 | 1.0 / 5.0 | 4,009.22 |
| LNI | 224.14 | 70 | 88 | 1.0 / 5.0 | 3,771.58 |
| LSI | 226.59 | 72 | 88 | 0.5 / 7.5 | 3,306.35 |
| UNI | 235.90 | 71 | 88 | 1.0 / 5.0 | 4,396.17 |
| USI | 238.01 | 75 | 88 | 0.5 / 7.5 | 3,790.37 |

Across the five Zones there are **361 scoped events**; adding **68 National events** produces the existing **429** scoped records, not unique market-wide episodes. Deduplicating by UTC interval gives **264** half-hours with any known Zone flagged. Grouping adjacent such half-hours, even when the flagged Zone changes, gives **108 analysis-only cross-regional episodes**. This leaves the approved event tables unchanged. [Overlap](../outputs/analysis/regional_overlap.csv), [episode boundaries](../outputs/analysis/cross_regional_episodes.csv)

All five Zones are simultaneously flagged in **104** half-hours, **59.09%** of National flagged intervals. **88** half-hours have Zone pressure without a National flag. Each Zone has **176** flagged intervals because its own P99 selects a similar tail size; equal counts do **not** mean equal price levels or risk. Event counts vary because persistence differs. Use an any-Zone indicator and simultaneous-Zone count beside National alerts, and do not add National and regional energy or event counts.

## 4. Higher demand is associated with pressure, with material exceptions [F4]

Mean demand was **5,371 MW** in pressure half-hours versus **4,794 MW** otherwise (**12.04% higher**). Medians were **5,335 / 4,886 MW**, and P95 demand **6,993 / 6,064 MW**. Half-hour peaks were **7,565 / 7,517 MW**, respectively. The groups contain **176 / 17,344** intervals. [Annual comparison](../outputs/analysis/demand_comparison.csv)

For each pressure interval, the contextual comparator is the mean of non-pressure intervals from the **same local month and hour**, then those means are averaged across pressure intervals. All **176** pressure observations matched, with at least **51** controls per stratum. The comparator mean rises to **5,032 MW**, leaving **339 MW (6.75%)** difference. It reduces, but does not eliminate, the annual association. [Adjusted comparison](../outputs/analysis/demand_hour_adjusted.json)

Within-month demand was higher in **9 of 10** months containing National flags. September was the exception (**22.80 MW lower**), and the low-demand case E5 shows why demand-only monitoring is inadequate. [Within-month evidence](../outputs/analysis/demand_within_month.csv), [derived differences](../outputs/analysis/derived_comparisons.json)

This comparison does not control for weather, weekdays, forecasts, outages or available capacity. Adjacent intervals share an episode and are not independent trials. The evidence supports a contextual monitoring comparison, not an estimate of how changing demand would change price.

## 5. Pressure has a larger fossil share, even though renewable output is higher [F5]

| Measure | Non-pressure | National pressure | Month/hour comparator |
|---|---|---|---|
| Listed output, mean MWh/half-hour | 2,360.34 | 2,662.26 | 2,480.81 |
| Renewable output, mean MWh/half-hour | 2,169.13 | 2,329.20 | 2,234.83 |
| Fossil output, mean MWh/half-hour | 127.16 | 286.53 | 194.80 |
| Storage output, mean MWh/half-hour | 2.64 | 6.84 | 3.65 |
| Unclassified output, mean MWh/half-hour | 61.40 | 39.69 | 47.54 |
| Renewable / classified primary, % | 94.46 | 89.05 | 91.98 |
| Classification / listed output, % | 97.40 | 98.51 | 98.08 |

The lower renewable **share** during pressure does not mean lower renewable **output**: mean renewable MWh per half-hour is higher in the pressure group, while fossil output increases more relative to its baseline. After month/hour standardisation, fossil output is **286.53 versus 194.80 MWh per half-hour** and renewable primary share is **89.05% versus 91.98%**, a difference of **-2.94 percentage points**. [Annual components](../outputs/analysis/generation_comparison.csv), [context-adjusted components](../outputs/analysis/generation_hour_adjusted.json)

Fossil primary share is **10.95%** during pressure versus **5.54%** otherwise; the month/hour comparator is **8.02%**. Unclassified output is **1.49%** of listed pressure output versus **2.60%** otherwise; storage is **0.26% / 0.11%**. As a sensitivity check only, treating all unclassified energy as non-renewable or renewable gives all-listed renewable bounds of **87.49–88.98%** under pressure versus **91.90–94.50%** otherwise. The annual direction persists within these bounds; the bounds use a different denominator from primary share and do not reclassify source codes or account for unlisted generation.

Monitor absolute MWh and share together. ELE/BAT remains Storage; no conclusion about battery state of charge, adequacy or causal price-setting follows from listed output. Higher thermal output can be a response to system conditions as well as a coincident characteristic; this design cannot distinguish those mechanisms.

## 6. Regional separation is much wider during pressure [F6]

| Population | Half-hours (all complete) | Mean spread | Median | P95 | Maximum |
|---|---|---|---|---|---|
| National pressure | 176 | 134.66 | 37.74 | 751.34 | 2,795.65 |
| No National or Zone pressure | 17256 | 12.66 | 7.28 | 41.90 | 230.11 |
| No National pressure | 17344 | 13.10 | 7.38 | 43.20 | 317.23 |
| Zone-only pressure | 88 | 98.31 | 48.84 | 251.49 | 317.23 |

All spread values are NZD/MWh, maximum minus minimum known-Zone weighted price in the same interval. National-pressure mean spread is **134.66**, versus **13.10** outside National pressure. The difference also appears in medians (**37.74 versus 7.38**), so the comparison is not solely the single largest outlier. Zone-only periods have mean spread **98.31**, supporting a regional investigation path even when the National flag is off. [Spread comparison](../outputs/analysis/spread_comparison.csv)

Every included interval meets the existing five-known-Zone completeness rule. [Each Zone's own pressure/non-pressure spread distributions](../outputs/analysis/spread_by_zone_pressure.csv) provide the additional regional cut without redefining spread. Unknown geography remains excluded from spread and included nationally. The comparison populations in this table overlap: do not sum their counts. Separation warrants inspection of node prices, system conditions and official reports; it is not itself evidence of congestion.

## 7. Contrasting cases show why several indicators are needed [F7]

Cases were selected by explicit data-first rules before official context retrieval. They are intentionally contrasting examples, not a random sample. Times below are Pacific/Auckland; event end is exclusive. E1 and E4 occur on the same evening but are separate National events because an intervening half-hour is below the threshold. E3's event price is CNI, while its supporting demand and generation context is National.

### E1 — 2026-08-04, 19:30–21:30 local (National)

**Selection:** Highest-peak National event with all five Zones flagged throughout. Exact ID: `National:National:202608040730`.

The event lasted **2.0 hours** across **4 half-hour interval(s)**. Its own-scope weighted price was **2,660.16**, peaking at **3,924.45 NZD/MWh**. National weighted price over the same window was **2,660.16**. National mean/peak demand was **6,936 / 7,071 MW**; the mean annual interval demand percentile was **99.64**.

National listed output averaged **3,506.91 MWh/half-hour**, including **0.27 storage** and **109.42 unclassified MWh**. Renewable primary share was **93.92%**. Mean/max known-Zone spread was **773.93 / 1,089.82 NZD/MWh**. Flagged Zone combinations were **CNI,LNI,LSI,UNI,USI**; these identify flags during the window, not every node exposed to high prices.

Coverage over this window: price weighting **100.00%**, Offtake Zone **99.9491%**, generation Zone **98.90%**, generation classification **96.88%**. Context generation and demand are National even for the CNI event. Full UTC boundaries and every scoped event are in [case evidence](../outputs/analysis/representative_events.json) and [event SQL output](../outputs/analysis/event_investigation.csv). [F7]

**External context, distinguished from our measurements:** EA connects the Tuesday evening high prices with thermal availability problems and reports an earlier reserve and wind forecast shortfall. It also reports that Ruakaka was depleted during the evening high-price periods. Relevant contemporaneous context for the selected evening, not a causal estimate from this project's data. Node/dispatch prices differ from Offtake-weighted National half-hours. The report's sections give inconsistent Huntly trip timing; do not assert an exact trip time. Storage output here is not state of charge. [Trading conduct report 2-8 August 2026](https://www.ea.govt.nz/documents/10708/Trading_conduct_report_02-08_August_2026_1.pdf), Sections 2.3-2.4, 7.11, 7.17, 7.20; printed pages 1, 9-11.

### E2 — 2025-09-06, 07:30–12:30 local (National)

**Selection:** Longest National event; earliest start breaks ties. Exact ID: `National:National:202509051930`.

The event lasted **5.0 hours** across **10 half-hour interval(s)**. Its own-scope weighted price was **253.66**, peaking at **278.22 NZD/MWh**. National weighted price over the same window was **253.66**. National mean/peak demand was **5,305 / 5,455 MW**; the mean annual interval demand percentile was **73.55**.

National listed output averaged **2,589.40 MWh/half-hour**, including **6.96 storage** and **28.29 unclassified MWh**. Renewable primary share was **92.81%**. Mean/max known-Zone spread was **29.43 / 42.95 NZD/MWh**. Flagged Zone combinations were **CNI,LNI,LSI,UNI,USI; CNI,LNI,UNI; CNI,LNI,UNI,USI**; these identify flags during the window, not every node exposed to high prices.

Coverage over this window: price weighting **100.00%**, Offtake Zone **100.0000%**, generation Zone **99.74%**, generation classification **98.91%**. Context generation and demand are National even for the CNI event. Full UTC boundaries and every scoped event are in [case evidence](../outputs/analysis/representative_events.json) and [event SQL output](../outputs/analysis/event_investigation.csv). [F7]

**External context, distinguished from our measurements:** EA describes declining Saturday wind and dispatch of thermal peakers in low-wind conditions. Day-level corroborating context, not proof of the cause of the entire selected morning event. The project does not contain wind forecasts, offers or dispatch counterfactuals. [Trading conduct report 31 August-6 September 2025](https://www.ea.govt.nz/documents/8360/Trading_Conduct_Report_31_Aug_-_6_Sept_2025.pdf), Sections 7.3 and 7.9; printed pages 6 and 8.

### E3 — 2026-03-03, 07:30–09:30 local (CNI)

**Selection:** Largest maximum spread among Zone events with no National flagged interval. Exact ID: `Zone:CNI:202603021830`.

The event lasted **2.0 hours** across **4 half-hour interval(s)**. Its own-scope weighted price was **362.38**, peaking at **412.92 NZD/MWh**. National weighted price over the same window was **186.05**. National mean/peak demand was **5,602 / 5,668 MW**; the mean annual interval demand percentile was **86.44**.

National listed output averaged **2,762.66 MWh/half-hour**, including **1.43 storage** and **48.08 unclassified MWh**. Renewable primary share was **93.88%**. Mean/max known-Zone spread was **228.54 / 260.31 NZD/MWh**. Flagged Zone combinations were **CNI**; these identify flags during the window, not every node exposed to high prices.

Coverage over this window: price weighting **100.00%**, Offtake Zone **99.9899%**, generation Zone **98.44%**, generation classification **98.26%**. Context generation and demand are National even for the CNI event. Full UTC boundaries and every scoped event are in [case evidence](../outputs/analysis/representative_events.json) and [event SQL output](../outputs/analysis/event_investigation.csv). [F7]

**External context, distinguished from our measurements:** EA attributes Tuesday and Wednesday morning Fernhill and Tuai node spikes to Hawke's Bay line constraints, with further monitoring indicated. Official node-level context consistent with investigating the CNI separation. No node-to-Zone contribution decomposition was performed; do not claim the entire Zone spread was caused by this constraint. [Trading conduct report 1-7 March 2026](https://www.ea.govt.nz/documents/9432/Trading_conduct_report_-_1_March_2026.pdf), Sections 2.4-2.5; printed page 1.

### E4 — 2026-08-04, 18:30–19:00 local (National)

**Selection:** Highest-peak isolated National half-hour. Exact ID: `National:National:202608040630`.

The event lasted **0.5 hours** across **1 half-hour interval(s)**. Its own-scope weighted price was **1,389.08**, peaking at **1,389.08 NZD/MWh**. National weighted price over the same window was **1,389.08**. National mean/peak demand was **7,288 / 7,288 MW**; the mean annual interval demand percentile was **99.94**.

National listed output averaged **3,639.72 MWh/half-hour**, including **0.15 storage** and **111.50 unclassified MWh**. Renewable primary share was **90.99%**. Mean/max known-Zone spread was **365.89 / 365.89 NZD/MWh**. Flagged Zone combinations were **CNI,LNI,LSI,UNI,USI**; these identify flags during the window, not every node exposed to high prices.

Coverage over this window: price weighting **100.00%**, Offtake Zone **99.9548%**, generation Zone **98.94%**, generation classification **96.94%**. Context generation and demand are National even for the CNI event. Full UTC boundaries and every scoped event are in [case evidence](../outputs/analysis/representative_events.json) and [event SQL output](../outputs/analysis/event_investigation.csv). [F7]

**External context, distinguished from our measurements:** EA reports a reserve and wind forecast shortfall during this earlier half-hour. This is contemporaneous context, not a causal estimate from the project. The later evening availability problems discussed for E1 should not be projected backwards onto this event. [EA report, section 2.4](https://www.ea.govt.nz/documents/10708/Trading_conduct_report_02-08_August_2026_1.pdf).

### E5 — 2026-03-30, 03:30–04:00 local (National)

**Selection:** Lowest mean-demand National event: counterexample to high-demand-only interpretation. Exact ID: `National:National:202603291430`.

The event lasted **0.5 hours** across **1 half-hour interval(s)**. Its own-scope weighted price was **243.81**, peaking at **243.81 NZD/MWh**. National weighted price over the same window was **243.81**. National mean/peak demand was **3,355 / 3,355 MW**; the mean annual interval demand percentile was **1.39**.

National listed output averaged **1,675.87 MWh/half-hour**, including **0.10 storage** and **37.17 unclassified MWh**. Renewable primary share was **86.00%**. Mean/max known-Zone spread was **58.87 / 58.87 NZD/MWh**. Flagged Zone combinations were **LNI,LSI,USI**; these identify flags during the window, not every node exposed to high prices.

Coverage over this window: price weighting **100.00%**, Offtake Zone **99.9866%**, generation Zone **97.38%**, generation classification **97.78%**. Context generation and demand are National even for the CNI event. Full UTC boundaries and every scoped event are in [case evidence](../outputs/analysis/representative_events.json) and [event SQL output](../outputs/analysis/event_investigation.csv). [F7]

**External context, distinguished from our measurements:** EA discusses forecast differences around some Monday high prices. No exact attribution to the selected 03:30 half-hour was established from the reviewed text. Retain the event as a descriptive counterexample with its cause unresolved. [Trading conduct report 29 March-4 April 2026](https://www.ea.govt.nz/documents/9576/Trading_conduct_report_-_29_March_2026.pdf), Sections 2.5 and 7.8-7.11; printed pages 1 and 7.



The longest case supports duration monitoring; the CNI case supports regional drill-through; the low-demand case prevents an overly narrow high-demand explanation. Official attribution remains attributed to the publisher, not established by these descriptive comparisons.

## Monitoring implications and further questions

Prioritise a National weighted-price/P95/volatility overview, a separate any-Zone pressure indicator, event duration and peak, the simultaneous-Zone count, and comparable month/hour demand. Put absolute renewable/fossil/storage/unclassified output alongside shares and coverage. Provide event-to-interval and Zone-to-node investigation paths; source limitations must remain available before users interpret a missing or extreme value.

Further investigation could test the contribution of individual POCs to CNI separation, and align official outage, reserve, wind-forecast and hydro evidence at the same interval grain. Those sources were not added to the approved release. The original recommendations are retained in [Power BI findings handoff](portfolio_case_study.md). The implemented report subsequently passed [Desktop runtime acceptance](desktop_acceptance.md); see the [screenshot gallery](powerbi_gallery.md).

## Limitations and evidence

- This single release supports descriptive associations and within-period variation, not multi-year seasonality, forecasts or causal estimates. Ex-post P99 and case selection use the whole year; do not present them as live predictive alerts.
- Source revisions can change both measurements and percentile membership. The retained DQ assessment is as-of **1 October 2026**. Unknown geography, quarantined invalid NSP ends, valid-history gaps, sparse/all-zero generation, I/X disagreement and historical freshness warnings remain intact; see [continuous-release validation](release_validation.md).
- Monthly price-node Zone coverage is **89.38–90.31% by rows**, Offtake Zone coverage **99.82–100% by kWh**, and generation Zone coverage **98.20–99.55% by kWh**. Price-node row coverage is not priced-demand coverage: National priced Offtake is fully covered in this release. Unknown energy remains in National totals; small aggregate missing shares need not be immaterial for an individual Zone or event. [Saved quality measures](../outputs/analysis/monthly_quality.csv)
- Monthly generation classification coverage is **95.52–98.63%** by listed energy. Unsupported exact codes stay Unclassified, so primary-share claims concern the classified subset. National generation can include unmapped rows without implying their geography is known. [Monthly overview](../outputs/analysis/monthly_overview.csv)
- Official reports use their own node, dispatch, timing and population definitions. They corroborate context; their values should not be substituted for this project's weighted metrics. Exact-time context remains unconfirmed for E5, and an internal trip-time discrepancy in the August report remains unresolved.
- Every finding ID maps to [findings evidence](../outputs/analysis/findings_evidence.csv), saved SQL results and [query hashes/read-only provenance](../outputs/analysis/query_manifest.json). [Methods and independent validation](analysis_validation.md) document recomputation and release integrity. No finding depends on a raw reload, modified classification or rewritten warehouse object.
