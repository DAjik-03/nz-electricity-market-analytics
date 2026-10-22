# Power BI interactions

This implemented contract is documented alongside the [model specification](powerbi_model_spec.md) and [visual register](powerbi_pages.md). Actual Desktop interactions passed [runtime acceptance](desktop_acceptance.md).

## Shared controls

- Pages 1–3: sync the DimDate[Date] Between slicer, default full release. Optional Weekday and Day Type controls are available in the filter pane; reset returns all 365 dates. These are local NZ dates.
- Pages 1–3: date selections affect interval facts and RegionalSignal only. Threshold and DemandBenchmark remain fixed. National event cards use start-date semantics and do not respond to hour/pressure slicers; label them “National events starting in selected dates”.
- Page 2 Zone selection: single-select DimZone[zone], default no selection so comparison axes show all five known Zones. Main price-comparison visuals have a **visual-level** filter excluding Unknown. Do not use a report-level Unknown exclusion. A separate Unknown quantity/coverage panel retains it. Selecting a Zone filters FactZone; it does not filter National, RegionalSignal or spread. Those panels are explicitly titled “National” or “All five known Zones”.
- Pages 1 and 3 have no Zone slicer. No visual uses a union of National and Zone rows. Zone subtotal/grand-total measures return blank.
- Page 3 optional National pressure-status slicer filters FactNational only. Do not synchronize it to other pages or present event/regional counts beside it as though identically filtered. Fixed benchmark panel remains full-release and is visually separated.
- Page 4: do **not** synchronize Date, hour or pressure slicers. Select exactly one Events[event_id]; multi/empty selection blanks detail measures. Scope/Zone fields from Events narrow its list; they do not filter DimZone. Keep all five known Zones in the participation heatmap. CaseContext follows Events selection; do not make a CaseContext slicer and expect reverse propagation.
- Page 5: separate DimMonth[Year-Month] selector for complete-month coverage, and source_name. It does not share the daily Between slicer. DQ cards, Release and Classification are fixed-release, unaffected by month/source selections. Do not suggest a partial-day coverage assessment.

## Clicks and drill-through

Use Edit interactions explicitly; choose **Filter** rather than partial highlight for ratio visuals. Page 1 monthly price and volatility charts filter the monthly detail table and date-sensitive cards. They do not filter the fixed P99 card. The narrative March/August annotation always says it describes the full release, so it cannot be mistaken for a recomputed filtered finding.

Page 2 Zone comparison bars filter the Zone detail visuals only. Turn off their interaction with National demand, all-Zone signal/spread and fixed-release regional totals. Month/date selections affect both grains through DimInterval. Do not enable bidirectional relationships to make chart clicks propagate.

Add a regional event table with Events[event_id], scope, zone, local_start, local_end and the scalar event measures; a **page-specific event list filter** should use Events[scope]="Zone". Its list is explicitly “Full-release regional events”; it is disconnected from the global date/DimZone filters. Users narrow it with Events[zone] and start_date in the visual/filter pane. This deliberate separation avoids silently dropping events that cross selected dates. Right-click an event row → Page 4, with Events[event_id] as the only drill-through field and **Keep all filters OFF**. Include a Back button. No date-only or Zone-only event drill-through.

Page 4 event selector filters the detail cards, CaseContext table and membership bridge. The heatmap uses DimInterval[start_utc] rows, DimZone[zone] columns, `[Zone Pressure Flag]`, and visual filter `[Event Interval Visible]=1`; known Zones only. Local time/TP/offset/fold belong in the tooltip. These are scoped Zone flags, not every node's price. If individual heatmap cells are clicked, disable filtering of event summary cards so full-event values stay whole.

The full-event cards ignore Date. A future interval-within-event metric must be explicitly labelled “selected part of event”; do not repurpose full Event Duration. Event end is exclusive. E1 and E4 remain separate events even on the same evening.

## Case presets / bookmarks

Create E1–E5 bookmarks on Page 4 from [case_presets.json](../powerbi/case_presets.json). For each, select its exact Events[event_id], then capture **Data ON, Current page ON, Selected visuals only**, selecting only the event-ID slicer. Clear other Events filters first. Display settings remain untouched. Buttons labelled E1…E5 invoke those bookmarks; add a reset-event bookmark with no selection. They do not capture Date or a Zone slicer.

| Preset | Exact event_id | Purpose |
|---|---|---|
| E1 | National:National:202608040730 | Broad extreme, 4 Aug 2026 19:30 local |
| E2 | National:National:202509051930 | Longest National event, 6 Sep 2025 07:30 |
| E3 | Zone:CNI:202603021830 | CNI separation, National below its threshold |
| E4 | National:National:202608040630 | Isolated extreme preceding E1 |
| E5 | National:National:202603291430 | Low-demand counterexample |

Official context is a separate table/card headed **Electricity Authority context — not a project causal estimate**. Show title, locator, URL, review date and qualification. Preserve E5's unresolved exact cause, August's inconsistent trip timing and E3's node-versus-Zone distinction. Do not turn local JSON paths into purported live report links.

## Tooltips and accessibility

Price: NZD/MWh, sum numerator/priced Offtake semantics, priced coverage, observed half-hours, fixed threshold population. Demand: Offtake GWh or mean/peak MW, scope and geography coverage. Generation: listed GWh, primary denominator, Storage/Unclassified quantities and classification coverage. Spread: five-known-Zone eligibility and eligible interval count. Event: event_id, scope/Zone, UTC/local boundaries, TP/offset/fold in detail, selected/full event distinction and coverage.

Use a 1280×800 canvas, ≥12pt labels, 24pt page headings, dark text on white/light grey, teal for price and orange for pressure. Use explicit PASS/WARN/FAIL words, not colour alone. Storage is purple, Unclassified grey; renewable green and fossil orange. Do not colour a higher price as intrinsically bad. Tab order: navigation → slicers → headline cards → charts → detail/context. Add descriptive alt text matching each visual's question. Tables provide an accessible alternative to chart colour/shape.

## Acceptance scenarios

1. Full release: National 68 events, 176 half-hours, 88 hours; all-Zone 264 half-hours/108 episodes/88 Zone-only. Never display 429 as a unique-market count.
2. Select March then August: all full-period P99 values remain unchanged, while monthly price/P95/SD follow the date selection. Clear selection restores totals.
3. Select CNI: Zone measures change; National demand and all-Zone spread/flags do not. Unknown remains nationally included.
4. Select two Zones: multi-Zone scalar measures blank; each Zone axis row remains valid; no sum of Zone peaks or P95s.
5. E3: scoped event price differs from National context; heatmap has one Zone flagged, and no National pressure. E1/E4 bookmarks show distinct memberships.
6. Filter Apr 5 fall-back and Sep 28 spring-forward: 50 and 46 rows, ordered in UTC, repeated local times distinguished. No date hierarchy reduces either to 48.
7. Page 5 change source/month: source denominator and coverage change, DQ remains 21/8/0. Selecting multiple sources blanks mixed-unit scalar coverage.
