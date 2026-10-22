"""Render the requested Markdown findings and claim register from reviewed SQL outputs."""
import csv
import json
from validate_findings import OUT, ROOT, load


def f(value, places=2):
    return f'{float(value):,.{places}f}'


def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])


def main():
    m=load('monthly_overview'); monthly={x['source_month'][:7]:x for x in m}
    d=load('demand_comparison'); adj=load('demand_hour_adjusted')[0]
    gen=load('generation_comparison'); ga=load('generation_hour_adjusted')[0]
    derived=load('derived_comparisons'); events=load('representative_events')
    dist=load('national_event_distribution')[0]; regional=load('regional_events')
    spr={x['population']:x for x in load('spread_comparison')}
    ext=load('external_context')['sources']; manifest=load('query_manifest')
    # Flat, readable companions; large interval extracts remain compressed JSON.
    for name,meta in manifest['queries'].items():
        rows=load(name)
        if rows and len(rows)<=500:
            with (OUT/(name+'.csv')).open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    sources={
        'F1':('How did observed monthly market conditions differ?',['monthly_overview','release_population']),
        'F2':('When and for how long did National pressure occur?',['national_event_distribution','pressure_by_month','pressure_by_hour','pressure_by_day_type','event_starts_by_month']),
        'F3':('How much did regional pressure overlap?',['regional_events','regional_overlap','cross_regional_episodes']),
        'F4':('Was demand higher during pressure after simple context adjustment?',['demand_comparison','demand_within_month','demand_hour_adjusted']),
        'F5':('How did absolute generation and energy shares differ?',['generation_comparison','generation_hour_adjusted']),
        'F6':('Did pressure coincide with wider known-Zone spreads?',['spread_comparison','spread_by_zone_pressure']),
        'F7':('Which contrasting episodes merit drill-through?',['event_investigation']),
    }
    qualifications={
        'F1':'Within this release only; month length differs; December uses audited final-daily aggregate; no multi-year seasonality.',
        'F2':'Full-year ex-post National P99; intervals, events and hours differ. Local hour exposure includes DST.',
        'F3':'Zone-specific ex-post thresholds; National and Zone events overlap. Any-Zone UTC episode is analysis-only.',
        'F4':'National includes Unknown. Month/hour comparator omits weather, weekday and outages; dependence within episodes; descriptive only.',
        'F5':'Classified primary denominator excludes Storage/Unclassified. Absolute listed generation differs from reconciled Offtake; unsupported codes unchanged.',
        'F6':'Only five-known-Zone-complete spreads; excludes Unknown geography. Larger spread alone does not establish congestion.',
        'F7':'Deliberately contrasting cases, not representative sample for incidence. Official context has different metrics and causal attribution limits.',
    }
    evidence=[]
    for fid,(question,names) in sources.items():
        for name in names:
            evidence.append(dict(finding_id=fid,analytical_question=question,metric=name,comparison_population=qualifications[fid],
                observed_result=json.dumps(load(name) if name not in ['event_investigation','cross_regional_episodes'] else (events if name=='event_investigation' else {'episode_count':len(load(name)),'unique_intervals':sum(x['intervals'] for x in load(name))}),separators=(',',':')),
                source_sql_query=manifest['queries'][name]['sql']+'#'+name,output_file='outputs/analysis/'+name+'.json',
                coverage_quality_qualification=qualifications[fid],external_source='; '.join(s['url'] for s in ext) if fid=='F7' else '',
                confidence_limitation_note='Reproduced from saved SQL; high confidence in descriptive calculation, no causal identification.'))
    evidence.append(dict(finding_id='F4',analytical_question='Within-month consistency and derived comparisons',metric='derived_comparisons',comparison_population='Pressure versus non-pressure within observed months',observed_result=json.dumps(derived,separators=(',',':')),source_sql_query='sql/05_analysis/04_demand_association.sql#demand_within_month; src/validate_findings.py',output_file='outputs/analysis/derived_comparisons.json',coverage_quality_qualification=qualifications['F4'],external_source='',confidence_limitation_note='Independent recomputation from saved interval SQL extract.'))
    with (OUT/'findings_evidence.csv').open('w',newline='',encoding='utf-8') as stream:
        w=csv.DictWriter(stream,fieldnames=list(evidence[0]));w.writeheader();w.writerows(evidence)
    monthly_table=table(['Month','Weighted price','P95','Price SD','Demand GWh','Peak MW','Listed generation GWh','Renewable primary %','Flagged half-hours'],[
        [x['source_month'][:7],f(x['weighted_price']),f(x['p95_interval_price']),f(x['price_volatility_pop']),f(x['demand_gwh']),f(x['peak_demand_mw'],0),f(x['listed_generation_gwh']),f(x['renewable_primary_share_pct']),x['high_price_intervals']] for x in m])
    regional_table=table(['Scope','P99 NZD/MWh','Events','Flagged hours','Median / max event hours','Peak NZD/MWh'],[
        [r['zone'],f(r['p99_price']),r['events'],f(r['flagged_hours'],0),f(r['median_event_hours'],1)+' / '+f(r['longest_event_hours'],1),f(r['peak_price'])] for r in regional])
    gen_table=table(['Measure','Non-pressure','National pressure','Month/hour comparator'],[
        ['Listed output, mean MWh/half-hour',f(gen[0]['mean_listed_mwh']),f(gen[1]['mean_listed_mwh']),f(ga['control_listed_mwh'])],
        ['Renewable output, mean MWh/half-hour',f(gen[0]['mean_renewable_mwh']),f(gen[1]['mean_renewable_mwh']),f(ga['control_renewable_mwh'])],
        ['Fossil output, mean MWh/half-hour',f(gen[0]['mean_fossil_mwh']),f(gen[1]['mean_fossil_mwh']),f(ga['control_fossil_mwh'])],
        ['Storage output, mean MWh/half-hour',f(gen[0]['mean_storage_mwh']),f(gen[1]['mean_storage_mwh']),f(ga['control_storage_mwh'])],
        ['Unclassified output, mean MWh/half-hour',f(gen[0]['mean_unclassified_mwh']),f(gen[1]['mean_unclassified_mwh']),f(ga['control_unclassified_mwh'])],
        ['Renewable / classified primary, %',f(gen[0]['renewable_primary_share_pct']),f(gen[1]['renewable_primary_share_pct']),f(ga['control_renewable_primary_pct'])],
        ['Classification / listed output, %',f(gen[0]['classification_coverage_pct']),f(gen[1]['classification_coverage_pct']),f(ga['control_classification_pct'])]])
    spread_table=table(['Population','Half-hours (all complete)','Mean spread','Median','P95','Maximum'],[[r['population'],r['intervals'],f(r['mean_spread']),f(r['median_spread']),f(r['p95_spread']),f(r['max_spread'])] for r in load('spread_comparison')])
    cases=[]
    for e in events:
        applicable=[s for s in ext if e['case_id'] in s['cases']]
        context=' '.join(s['supported_context']+' '+s['qualification']+' ['+s['title']+']('+s['url']+'), '+s['locator']+'.' for s in applicable)
        if e['case_id']=='E4':
            context="EA reports a reserve and wind forecast shortfall during this earlier half-hour. This is contemporaneous context, not a causal estimate from the project. The later evening availability problems discussed for E1 should not be projected backwards onto this event. [EA report, section 2.4]("+applicable[0]['url']+")."
        cases.append(f"""### {e['case_id']} — {e['local_start'][:10]}, {e['local_start'][11:16]}–{e['local_end'][11:16]} local ({e['zone']})

**Selection:** {e['selection_reason']}. Exact ID: `{e['event_id']}`.

The event lasted **{f(e['duration_hours'],1)} hours** across **{e['interval_count']} half-hour interval(s)**. Its own-scope weighted price was **{f(e['weighted_price'])}**, peaking at **{f(e['peak_weighted_price'])} NZD/MWh**. National weighted price over the same window was **{f(e['national_weighted_price'])}**. National mean/peak demand was **{f(e['national_mean_demand_mw'],0)} / {f(e['national_peak_demand_mw'],0)} MW**; the mean annual interval demand percentile was **{f(e['mean_annual_demand_percentile'])}**.

National listed output averaged **{f(e['national_mean_listed_mwh'])} MWh/half-hour**, including **{f(e['national_mean_storage_mwh'])} storage** and **{f(e['national_mean_unclassified_mwh'])} unclassified MWh**. Renewable primary share was **{f(e['national_renewable_primary_pct'])}%**. Mean/max known-Zone spread was **{f(e['mean_spread'])} / {f(e['max_spread'])} NZD/MWh**. Flagged Zone combinations were **{e['zone_combinations']}**; these identify flags during the window, not every node exposed to high prices.

Coverage over this window: price weighting **{f(e['price_coverage_pct'])}%**, Offtake Zone **{f(e['offtake_zone_coverage_pct'],4)}%**, generation Zone **{f(e['generation_zone_coverage_pct'])}%**, generation classification **{f(e['national_classification_pct'])}%**. Context generation and demand are National even for the CNI event. Full UTC boundaries and every scoped event are in [case evidence](../outputs/analysis/representative_events.json) and [event SQL output](../outputs/analysis/event_investigation.csv). [F7]

**External context, distinguished from our measurements:** {context}

""")
    report=f"""# NZ wholesale price pressure: conditions to monitor

## Executive Summary

- **Monitor persistent pressure and isolated extremes separately.** September and March account for **{f(derived['september_march_pressure_share_pct'],1)}%** of National flagged half-hours, while August contains the largest observed spike. Monthly average price alone would miss this distinction. [F1, F2]
- **Demand and generation mix are useful context, not sufficient explanations.** Pressure-period demand remains **{f(adj['difference_pct'])}% higher** after comparing the same month and local hour; renewable primary share is **{f(ga['pressure_renewable_primary_pct'])}% versus {f(ga['control_renewable_primary_pct'])}%** in that comparator. Some pressure nevertheless occurs at low demand. [F4, F5, F7]
- **National monitoring needs a regional drill-through.** **{derived['zone_only_intervals']} half-hours** have Zone pressure without National pressure. Regional spreads are much wider during pressure, but spread alone does not prove a transmission constraint. [F3, F6]
- **Use coverage and official event context alongside indicators.** Keep Unknown geography, unclassified generation and revision status visible. The selected cases support investigation priorities, not causal, investment or policy recommendations. [F7]

## Reading the measures

The approved release covers **1 September 2025–31 August 2026**, with **17,520 National half-hours**. Prices are **NZD/MWh**, weighted by priced reconciled Offtake. Demand means Offtake, including Unknown geography nationally. A National pressure interval has weighted price at or above the stored full-precision P99 **227.84134669510667**; each Zone has its own threshold. An event is contiguous flagged UTC half-hours within one scope. These are retrospective, project-defined thresholds, not official scarcity or compliance classifications. Approximately one percent flagged per scope is a consequence of the full-period percentile definition, not a prospective risk estimate. [F1–F3]

Primary renewable/fossil shares use only classified primary generation as denominator. Storage and Unclassified are shown separately against all listed generation. Listed output is not gross national generation and is not an energy-balance identity with Offtake. Equal-interval statistics and energy-weighted prices answer different questions. [F5; [metric dictionary](kpi_dictionary.md)]

## 1. Monthly conditions: highest average and greatest volatility differ [F1]

March's weighted price was **{f(monthly['2026-03']['weighted_price'])}**, compared with **{f(monthly['2026-01']['weighted_price'])} in January**, a difference of **{f(float(monthly['2026-03']['weighted_price'])-float(monthly['2026-01']['weighted_price']))} NZD/MWh**. August's average was **{f(monthly['2026-08']['weighted_price'])}**, but its interval price SD was **{f(monthly['2026-08']['price_volatility_pop'])}**, compared with March's **{f(monthly['2026-03']['price_volatility_pop'])}**. Thus higher typical exposure and larger occasional extremes were different monitoring problems in this period.

{monthly_table}

Prices, P95 and SD are NZD/MWh. This is **within-period monthly variation**, not established seasonal behaviour. Monthly demand totals also differ with calendar length; compare peak/interval demand for intensity. [Full monthly components, including fossil/storage/unclassified shares and spread](../outputs/analysis/monthly_overview.csv) preserve every requested overview metric. For analysts, show monthly exposure alongside tail and volatility measures rather than a single best/worst ranking.

## 2. Pressure clusters in months and hours, with different event lengths [F2]

There were **{dist['events']} National events**, comprising **{dist['intervals']} flagged half-hours** and **{f(dist['hours'],0)} hours**. **{dist['isolated_events']} events** were isolated half-hours; median duration was **{f(dist['duration_p50_p95'][0],1)} hour**, P95 duration **{f(dist['duration_p50_p95'][1],1)} hours**, and the longest **{f(dist['maximum_hours'],1)} hours**. Median event peak price was **{f(dist['event_peak_p50_p95'][0])}** and P95 event peak **{f(dist['event_peak_p50_p95'][1])} NZD/MWh**. Peak-price distribution is across events, not across all intervals. [Distribution](../outputs/analysis/national_event_distribution.json)

March contributed **63** flagged half-hours and September **49**, together **{f(derived['september_march_pressure_share_pct'],1)}%** of the total. Their within-month flag rates were **4.23%** and **3.41%**; January and February had no National flags. At local **07:00–07:59**, **26 of 730** half-hours were flagged (**3.56%**), versus **17 of 730 (2.33%)** at **18:00–18:59**. Weekday and weekend rates were **1.21%** and **0.50%**, respectively. These cuts are descriptive and correlated with month and demand, not independent risk factors. [Month](../outputs/analysis/pressure_by_month.csv), [hour](../outputs/analysis/pressure_by_hour.csv), [day type](../outputs/analysis/pressure_by_day_type.csv)

The monitoring implication is to retain both duration and peak: a long moderately high episode can matter differently from a single extreme half-hour. Use interval counts/rates for timing; [event starts by month](../outputs/analysis/event_starts_by_month.csv) assign an event to its start month and must not substitute for interval exposure.

## 3. Regional flags overlap substantially, but National misses some local pressure [F3]

{regional_table}

Across the five Zones there are **361 scoped events**; adding **68 National events** produces the existing **429** scoped records, not unique market-wide episodes. Deduplicating by UTC interval gives **264** half-hours with any known Zone flagged. Grouping adjacent such half-hours, even when the flagged Zone changes, gives **108 analysis-only cross-regional episodes**. This leaves the approved event tables unchanged. [Overlap](../outputs/analysis/regional_overlap.csv), [episode boundaries](../outputs/analysis/cross_regional_episodes.csv)

All five Zones are simultaneously flagged in **104** half-hours, **59.09%** of National flagged intervals. **88** half-hours have Zone pressure without a National flag. Each Zone has **176** flagged intervals because its own P99 selects a similar tail size; equal counts do **not** mean equal price levels or risk. Event counts vary because persistence differs. Use an any-Zone indicator and simultaneous-Zone count beside National alerts, and do not add National and regional energy or event counts.

## 4. Higher demand is associated with pressure, with material exceptions [F4]

Mean demand was **{f(d[1]['mean_demand_mw'],0)} MW** in pressure half-hours versus **{f(d[0]['mean_demand_mw'],0)} MW** otherwise (**{f(derived['annual_demand_difference_pct'])}% higher**). Medians were **{f(d[1]['median_demand_mw'],0)} / {f(d[0]['median_demand_mw'],0)} MW**, and P95 demand **{f(d[1]['p95_demand_mw'],0)} / {f(d[0]['p95_demand_mw'],0)} MW**. Half-hour peaks were **{f(d[1]['peak_demand_mw'],0)} / {f(d[0]['peak_demand_mw'],0)} MW**, respectively. The groups contain **176 / 17,344** intervals. [Annual comparison](../outputs/analysis/demand_comparison.csv)

For each pressure interval, the contextual comparator is the mean of non-pressure intervals from the **same local month and hour**, then those means are averaged across pressure intervals. All **176** pressure observations matched, with at least **51** controls per stratum. The comparator mean rises to **{f(adj['matched_control_mean_mw'],0)} MW**, leaving **{f(adj['mean_difference_mw'],0)} MW ({f(adj['difference_pct'])}%)** difference. It reduces, but does not eliminate, the annual association. [Adjusted comparison](../outputs/analysis/demand_hour_adjusted.json)

Within-month demand was higher in **9 of 10** months containing National flags. September was the exception (**22.80 MW lower**), and the low-demand case E5 shows why demand-only monitoring is inadequate. [Within-month evidence](../outputs/analysis/demand_within_month.csv), [derived differences](../outputs/analysis/derived_comparisons.json)

This comparison does not control for weather, weekdays, forecasts, outages or available capacity. Adjacent intervals share an episode and are not independent trials. The evidence supports a contextual monitoring comparison, not an estimate of how changing demand would change price.

## 5. Pressure has a larger fossil share, even though renewable output is higher [F5]

{gen_table}

The lower renewable **share** during pressure does not mean lower renewable **output**: mean renewable MWh per half-hour is higher in the pressure group, while fossil output increases more relative to its baseline. After month/hour standardisation, fossil output is **{f(ga['pressure_fossil_mwh'])} versus {f(ga['control_fossil_mwh'])} MWh per half-hour** and renewable primary share is **{f(ga['pressure_renewable_primary_pct'])}% versus {f(ga['control_renewable_primary_pct'])}%**, a difference of **{f(float(ga['pressure_renewable_primary_pct'])-float(ga['control_renewable_primary_pct']))} percentage points**. [Annual components](../outputs/analysis/generation_comparison.csv), [context-adjusted components](../outputs/analysis/generation_hour_adjusted.json)

Fossil primary share is **{f(gen[1]['fossil_primary_share_pct'])}%** during pressure versus **{f(gen[0]['fossil_primary_share_pct'])}%** otherwise; the month/hour comparator is **{f(100-float(ga['control_renewable_primary_pct']))}%**. Unclassified output is **{f(gen[1]['unclassified_listed_share_pct'])}%** of listed pressure output versus **{f(gen[0]['unclassified_listed_share_pct'])}%** otherwise; storage is **{f(gen[1]['storage_listed_share_pct'])}% / {f(gen[0]['storage_listed_share_pct'])}%**. As a sensitivity check only, treating all unclassified energy as non-renewable or renewable gives all-listed renewable bounds of **{f(gen[1]['renewable_all_listed_lower_pct'])}–{f(gen[1]['renewable_all_listed_upper_pct'])}%** under pressure versus **{f(gen[0]['renewable_all_listed_lower_pct'])}–{f(gen[0]['renewable_all_listed_upper_pct'])}%** otherwise. The annual direction persists within these bounds; the bounds use a different denominator from primary share and do not reclassify source codes or account for unlisted generation.

Monitor absolute MWh and share together. ELE/BAT remains Storage; no conclusion about battery state of charge, adequacy or causal price-setting follows from listed output. Higher thermal output can be a response to system conditions as well as a coincident characteristic; this design cannot distinguish those mechanisms.

## 6. Regional separation is much wider during pressure [F6]

{spread_table}

All spread values are NZD/MWh, maximum minus minimum known-Zone weighted price in the same interval. National-pressure mean spread is **{f(spr['National pressure']['mean_spread'])}**, versus **{f(spr['No National pressure']['mean_spread'])}** outside National pressure. The difference also appears in medians (**{f(spr['National pressure']['median_spread'])} versus {f(spr['No National pressure']['median_spread'])}**), so the comparison is not solely the single largest outlier. Zone-only periods have mean spread **{f(spr['Zone-only pressure']['mean_spread'])}**, supporting a regional investigation path even when the National flag is off. [Spread comparison](../outputs/analysis/spread_comparison.csv)

Every included interval meets the existing five-known-Zone completeness rule. [Each Zone's own pressure/non-pressure spread distributions](../outputs/analysis/spread_by_zone_pressure.csv) provide the additional regional cut without redefining spread. Unknown geography remains excluded from spread and included nationally. The comparison populations in this table overlap: do not sum their counts. Separation warrants inspection of node prices, system conditions and official reports; it is not itself evidence of congestion.

## 7. Contrasting cases show why several indicators are needed [F7]

Cases were selected by explicit data-first rules before official context retrieval. They are intentionally contrasting examples, not a random sample. Times below are Pacific/Auckland; event end is exclusive. E1 and E4 occur on the same evening but are separate National events because an intervening half-hour is below the threshold. E3's event price is CNI, while its supporting demand and generation context is National.

{''.join(cases)}

The longest case supports duration monitoring; the CNI case supports regional drill-through; the low-demand case prevents an overly narrow high-demand explanation. Official attribution remains attributed to the publisher, not established by these descriptive comparisons.

## Monitoring implications and further questions

Prioritise a National weighted-price/P95/volatility overview, a separate any-Zone pressure indicator, event duration and peak, the simultaneous-Zone count, and comparable month/hour demand. Put absolute renewable/fossil/storage/unclassified output alongside shares and coverage. Provide event-to-interval and Zone-to-node investigation paths; source limitations must remain available before users interpret a missing or extreme value.

Further investigation could test the contribution of individual POCs to CNI separation, and align official outage, reserve, wind-forecast and hydro evidence at the same interval grain. Those sources were not added to the approved release. Dashboard design recommendations are in [Power BI findings handoff](powerbi_findings_handoff.md); no Power BI implementation is included.

## Limitations and evidence

- This single release supports descriptive associations and within-period variation, not multi-year seasonality, forecasts or causal estimates. Ex-post P99 and case selection use the whole year; do not present them as live predictive alerts.
- Source revisions can change both measurements and percentile membership. The retained DQ assessment is as-of **1 October 2026**. Unknown geography, quarantined invalid NSP ends, valid-history gaps, sparse/all-zero generation, I/X disagreement and historical freshness warnings remain intact; see [Phase 4B validation](phase4b_validation.md).
- Monthly price-node Zone coverage is **89.38–90.31% by rows**, Offtake Zone coverage **99.82–100% by kWh**, and generation Zone coverage **98.20–99.55% by kWh**. Price-node row coverage is not priced-demand coverage: National priced Offtake is fully covered in this release. Unknown energy remains in National totals; small aggregate missing shares need not be immaterial for an individual Zone or event. [Saved quality measures](../outputs/analysis/monthly_quality.csv)
- Monthly generation classification coverage is **95.52–98.63%** by listed energy. Unsupported exact codes stay Unclassified, so primary-share claims concern the classified subset. National generation can include unmapped rows without implying their geography is known. [Monthly overview](../outputs/analysis/monthly_overview.csv)
- Official reports use their own node, dispatch, timing and population definitions. They corroborate context; their values should not be substituted for this project's weighted metrics. Exact-time context remains unconfirmed for E5, and an internal trip-time discrepancy in the August report remains unresolved.
- Every finding ID maps to [findings evidence](../outputs/analysis/findings_evidence.csv), saved SQL results and [query hashes/read-only provenance](../outputs/analysis/query_manifest.json). [Methods and independent validation](phase5_validation.md) document recomputation and release integrity. No finding depends on a raw reload, modified classification or rewritten warehouse object.
"""
    (ROOT/'docs/findings.md').write_text(report,encoding='utf-8')
    print('Wrote findings.md, findings_evidence.csv and bounded query CSV companions')


if __name__=='__main__': main()
