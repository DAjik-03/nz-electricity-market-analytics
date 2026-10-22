# Investigating New Zealand electricity price pressure

## Executive Summary

**A national average can conceal local pressure and short-lived extremes.** This project combines official Electricity Authority data, a PostgreSQL warehouse and a five-page Power BI report to investigate when wholesale prices were elevated, where pressure occurred and which conditions were associated with it.

The continuous September 2025–August 2026 release contains 37 selected publications and 17,520 half-hour intervals. The analysis distinguishes sustained March price exposure from August volatility and identifies 88 half-hours of regional pressure without a National flag. It is a completed portfolio implementation, not a production service or a causal model.

## Business question and scope

How could an analyst monitor wholesale price exposure without overlooking regional differences, extreme events or gaps in data coverage? A useful answer needs more than a monthly average: duration, tail prices, demand, generation mix and source quality must be visible together.

Four official source families underpin the work: wholesale prices, reconciled injection/offtake, generation by plant and connection, and the network supply point (NSP) register. The [source audit](source_audit.md) records official locations, actual schemas and limitations. Twelve monthly slots per family plus one NSP snapshot form the 37-publication release. The December price slot is a traceable aggregate of 31 official final daily files because the monthly file was incomplete; see the [source decision](december_source_decision.md). Dates use Pacific/Auckland, including actual 46- and 50-period DST days.

The warehouse contains **71,843,944 reconciled-volume rows**, alongside price and generation facts. This is a storage population, not a count of independent observations or customers. [Release validation](release_validation.md)

## From published files to a usable report

[Architecture overview](portfolio_architecture.md) explains the complete path: immutable files and SHA-256 manifests, Python ingestion, PostgreSQL staging and core facts, SQL quality rules, analytical marts, evidence-backed findings, and Power BI Import.

The important modelling choices were driven by actual data:

- Preserve price at interval + pricing POC; reconciled volume at interval + POC + network + participant + flow direction; and generation at interval + generator code + POC + network.
- Derive demand from Offtake. Keep National and Zone analytical tables separate so their totals cannot be added or multiplied accidentally.
- Map geography using effective NSP validity; retain unmapped energy as Unknown rather than inferring a location. Preserve three invalid historical NSP boundaries in quarantine.
- Use UTC interval identity and date-specific local trading periods. Repeated local clocks on fall-back days remain distinguishable.
- Keep unsupported fuel codes Unclassified and storage separate from classified primary generation. A lower renewable share is not equivalent to lower renewable output.

The SQL quality framework has **29 rules: 21 PASS, 8 WARN, 0 FAIL** in retained run 5, as of 1 October 2026. Known exceptions stay warnings with diagnostics. Repeat runs and analytical refreshes were checked for substantive determinism; the saved regression suite records 103 passing tests. These are historical validation results, not tests rerun for this case study. [Quality framework](data_quality_framework.md) · [Test evidence](../outputs/analysis/full_test_results.json)

## Seven findings that change what to monitor

Prices below are NZD/MWh, weighted by priced reconciled Offtake. A pressure half-hour meets its scope's fixed, full-release P99; the National threshold is 227.84134669510667. Contiguous flagged UTC half-hours form an event. These are retrospective project definitions, not official scarcity classifications or predictive alerts.

1. **Typical exposure and extremes need separate indicators.** March's weighted price was 152.38 versus August's 82.30, but August's interval-price standard deviation was 167.53 versus March's 52.09. Monitor average exposure alongside volatility and peaks. [F1](findings.md#1-monthly-conditions-highest-average-and-greatest-volatility-differ-f1)
2. **Pressure was concentrated but varied in duration.** The 68 National events comprised 176 half-hours; 28 were single half-hours and the longest lasted five hours. March and September contributed 63.6% of flagged half-hours. This supports duration and peak monitoring rather than an event count alone. [F2](findings.md#2-pressure-clusters-in-months-and-hours-with-different-event-lengths-f2)
3. **The National P99 indicator did not capture some regional pressure.** There were 264 half-hours with any known Zone flagged, including 88 with no National flag. Regional episodes are deduplicated across Zones; scoped event counts must not be added as independent market events. [F3](findings.md#3-regional-flags-overlap-substantially-but-the-national-p99-indicator-does-not-capture-some-local-pressure-f3)
4. **Higher demand was associated with pressure, even within month/hour comparisons.** Pressure-period demand was 6.75% above a comparator drawn from non-pressure intervals in the same local month and hour. Weather, outages and other confounders were not controlled; this is not a demand-to-price causal estimate. [F4](findings.md#4-higher-demand-is-associated-with-pressure-with-material-exceptions-f4)
5. **Generation shares and absolute output tell different stories.** Renewable primary share was 89.05% during pressure versus 91.98% in the month/hour comparator, while absolute renewable output was higher. Show MWh, shares and classification coverage together. [F5](findings.md#5-pressure-has-a-larger-fossil-share-even-though-renewable-output-is-higher-f5)
6. **Regional price separation was wider during pressure.** Mean known-Zone spread was 134.66 during National pressure versus 13.10 outside it. This warrants regional investigation; it does not by itself establish congestion. [F6](findings.md#6-regional-separation-is-much-wider-during-pressure-f6)
7. **Contrasting cases prevent oversimplification.** E3 had CNI weighted price 362.38 while National price was 186.05 and unflagged; E5 occurred at low demand. Event review needs scope, timing and separately attributed official context. [F7](findings.md#7-contrasting-cases-show-why-several-indicators-are-needed-f7)

The Executive page pairs monthly exposure with volatility and regional pressure. The image is a genuine saved/reopened Desktop capture; click it for the full-resolution view.

![Executive Market Monitor](assets/powerbi/executive.jpg)

## Power BI solution

The native PBIP contains TMDL model definitions and PBIR report definitions: **16 loaded tables, eight active single-direction relationships, 59 DAX measures and five pages**. Executive, Regional, Generation, Investigation and Data Quality pages form a path from overview to event evidence and limitations. [Screenshot gallery](powerbi_gallery.md)

The E3 view deliberately separates the selected CNI event from National context. Its four-interval timeline and independent National price explain why a local flag can coexist with an unflagged National result.

![CNI event E3 with separate National context](assets/powerbi/investigation-E3.jpg)

Desktop acceptance included 19 numerical checks, 16 table row counts, E1–E5 presets, Reset, drill-through/Back and fixed-P99 behaviour under March/August filters. The neutral project was saved, fully closed and reopened successfully in **Store Desktop 2.159.883.0**. Public schema validation is explicitly partial because Microsoft's visualContainer 2.14 schema returned 404; real Desktop runtime acceptance remains recorded. [Acceptance evidence](desktop_acceptance.md)

## Limitations and next questions

One year supports within-period descriptions, not established multi-year seasonality. Source revisions can change results. Unknown geography, sparse generation, classification gaps and quarantined NSP dates remain visible; listed generation is not a national supply-demand balance. The ex-post P99 selects roughly one per cent of intervals by construction. Case selection was purposeful, not random.

The practical next question is whether node-level prices, reserve availability, outages, wind forecasts and hydro conditions explain particular events. That investigation is outside this release. The implemented report supports investigation and communication; it does not prescribe trading, investment or policy actions.

## Professional contribution

This project demonstrates SQL-led data modelling, defensible KPI design, testing against real source exceptions, Power BI modelling and the ability to communicate a finding with its denominator and limitations. Python supports ingestion and validation; the substantive transformations and analytical products are SQL. The output is a reviewable analytical workflow rather than a claim of production deployment or machine learning.
