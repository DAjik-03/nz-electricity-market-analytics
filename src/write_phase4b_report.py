"""Render final technical acceptance only after all required evidence passes."""
import json
import calendar
from collections import Counter
from datetime import datetime
from pathlib import Path
from warehouse.db import ROOT


def read(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))

def main():
    e=read('outputs/scale_up/final_evidence.json')
    final_database_bytes=e.get('post_test_state',{}).get('database_bytes',e['database_bytes'])
    final_host_free=e.get('post_test_state',{}).get('host_free_bytes',e['host_disk']['free'])
    tests=read('outputs/scale_up/final_tests.json')
    dq=read('outputs/data_quality/latest_summary.json')
    dd=read('outputs/data_quality/determinism.json')
    ad=read('outputs/analytics/determinism.json')
    validation=read('outputs/analytics/validation.json')
    archive=read('outputs/scale_up/archive_integrity.json')
    candidate=read('outputs/scale_up/candidate_validation.json')
    generation_profile=read('outputs/scale_up/generation_source_profile.json')
    if candidate['status']!='validated_and_promoted': raise ValueError('Candidate not accepted/promoted')
    if archive['files']!=34 or archive['git_normalised_hash_mismatches']!=0:
        raise ValueError('Pilot archive integrity not accepted')
    if tests['failures'] or tests['errors'] or tests['skipped']: raise ValueError('Tests not fully passing')
    if dq['blocking_failures'] or dq['run']['status']!='COMPLETED': raise ValueError('DQ not accepted')
    if not dd['passed'] or not all(ad['checks'].values()) or not all(validation['checks'].values()):
        raise ValueError('Validation/determinism not accepted')
    monthly=sorted([x for x in read('outputs/analytics/monthly.json') if x['scope']=='National'],key=lambda x:x['source_month'])
    if len(monthly)!=12 or len(dq['coverage'])!=36: raise ValueError('Incomplete release evidence')
    thresholds=read('outputs/analytics/thresholds.json')
    events=Counter(x['zone'] for x in read('outputs/analytics/events.json'))
    manifest=read('outputs/scale_up/source_manifest.json')
    pilot=read('outputs/pilot/source_manifest.json')
    old={pilot['versions'][v]['sha256'] for v in pilot['selected'].values()}
    pubs={p['publication_id']:p for p in e['publications']}
    new={pid for pid,p in pubs.items() if p['sha256'] not in old}
    attempts=[a for a in e['load_attempts'] if a['publication_id'] in new and a['status']=='succeeded']
    selected_bytes=sum(manifest['versions'][v]['bytes'] for v in manifest['selected'].values())
    cover={(v['source_name'],v['source_month']):v['coverage_pct'] for v in dq['coverage']}
    lines=['# Phase 4B historical release validation','',
      'The continuous 2025-09-01 through 2026-08-31 technical release is validated. Stop for review before Phase 5; no market findings, causal claims, YoY or Power BI are included.','',
      '## Source and warehouse acceptance','',
      'All 37 slots are loaded and selected atomically: twelve each of prices, reconciled volumes and generation plus the retained NSP snapshot. Ten original publications were reused unchanged; 27 new publications comprise 26 official monthly files and one derived December price publication. No observed pilot revision changed.','',
      'December source exception: 31 official final daily files produce 361,584 unique rows. The incomplete monthly diagnostic has 349,920 matching rows; its missing portion is 11,664 rows on 31 December. Zero overlapping price conflicts. The diagnostic remains ineligible. The deterministic aggregate retains all constituent filenames, URLs, dates, SHA-256 and retrieval/final-status metadata. See [source decision](december_source_decision.md) and metadata.v_source_packaging / metadata.v_source_constituent. Price grain remains interval + pricing POC.','',
      '| Core fact | Exact rows |','|---|---:|']
    lines += [f'| {name} | {count:,} |' for name,count in e['fact_counts'].items()]
    by_slot={p['slot']:p for p in candidate['publications']}
    lines += ['','| Month | Price rows | Reconciled volume rows | Generation interval rows |','|---|---:|---:|---:|']
    for month in sorted(generation_profile['months']):
        counts=[by_slot[f'{s}/{month}']['fact_rows'] for s in ['prices','reconciliation','generation']]
        lines.append('| '+month+' | '+' | '.join(f'{n:,}' for n in counts)+' |')
    lines += ['',f'Selection fingerprint: `{candidate["selection_identity_after"]["sha256"]}`. The ordered identity rows and hashing definition are retained in candidate_validation.json; the pre-promotion selection contained ten original pilot slots and the promoted selection contains 37.','',
              '| Recovered month | Publication | Flow | Exact source/core rows | Exact native kWh (both staging and core) |',
              '|---|---:|---|---:|---:|']
    for p in candidate['publications']:
        if p['slot'] in ('reconciliation/2026-06','reconciliation/2026-07'):
            for flow,rows,kwh in p['native_totals']['core']:
                lines.append(f'| {p["slot"].split("/")[1]} | {p["publication_id"]} | {flow} | {rows:,} | {kwh} |')
    lines += ['',f'Calendar: {e["calendar"][2]} local dates and {e["calendar"][3]:,} intervals. Real 2025-09-28 / 2026-04-05 source populations retain 46 / 50 periods. Source-aligned staging and normalised native totals reconcile; original pilot hash/count/total regression remains exact. Approved PK/FK/grain constraints are retained.','',
      '## Data quality and coverage','',f'Run {dq["run"]["run_id"]}, as-of {dq["run"]["as_of_date"]}: {dq["active_rules"]} rules; PASS {dq["counts"]["PASS"]} / WARN {dq["counts"]["WARN"]} / FAIL {dq["counts"]["FAIL"]}; blocking failures {dq["blocking_failures"]}. Repeated substantive DQ results match. Original immutable baselines remain separate from the explicit 37-slot required release configuration.','',
      '| Month | Price known Zone % (rows) | Offtake known Zone % (kWh) | Generation known Zone % (kWh) | Generation classification % (kWh) | Priced Offtake % |',
      '|---|---:|---:|---:|---:|---:|']
    for m in monthly:
        date=m['source_month']
        vals=[cover['prices',date],cover['reconciliation_offtake',date],cover['generation',date],m['classification_coverage_pct'],m['price_weighting_coverage_pct']]
        lines.append('| '+date[:7]+' | '+' | '.join(f'{v:.6f}' if v is not None else 'NULL' for v in vals)+' |')
    lines+=['','Known Zone coverage complements retained Unknown; it never authorises invented mappings or exclusion from national totals. Classification excludes unsupported code pairs and reports storage separately. The twelve-month union contains the same 14 fuel/technology pairs observed across the original pilot, with no new pair. Individual months contain 13 pairs through February 2026 and 14 thereafter; the earlier wording that every month contained 14 pairs was inaccurate.','',
      '| Month | Raw code pairs | All-zero daily rows | Sparse connection series | All-zero series-months | I/X disagreement source rows | I/X affected kWh |',
      '|---|---:|---:|---:|---:|---:|---:|']
    rules={r['rule_snapshot']['rule_code']:r for r in dq['results']}
    zero_series=Counter(d['source_month'][:7] for d in rules['DQ26']['observed_value']['diagnostics'] if d['all_zero'])
    ix={r['source_month'][:7]:r for r in rules['DQ27']['observed_value']}
    for month,p in sorted(generation_profile['months'].items()):
        year,mon=map(int,month.split('-'));days=calendar.monthrange(year,mon)[1]
        sparse=sum(r['observed_dates']<days for r in p['series_date_counts'])
        flow=ix.get(month,dict(affected_source_rows=0,affected_kwh=0))
        lines.append(f'| {month} | {len(p["pairs"])} | {p["all_zero_daily_rows"]} | {sparse} | {zero_series[month]} | {flow["affected_source_rows"]:,} | {flow["affected_kwh"]:,.6f} |')
    lines+=['','Raw daily zero counts and sparse series use the retained source profile; all-zero series-months and I/X diagnostics use the new DQ run. Sparse activity does not establish missing publication data or commissioning dates.','',
      '| Retained warning | Affected count (rule-specific unit) |','|---|---:|']
    lines += [f'| {r["rule_snapshot"]["rule_code"]}: {r["rule_snapshot"]["rule_name"]} | {r["affected_rows"]:,} |' for r in dq['results'] if r['result_status']=='WARN']
    lines += ['','| Source | Latest selected period end | Days to assessment | Revision/finality state |','|---|---|---:|---|']
    for r in rules['DQ28']['observed_value']:
        lines.append(f'| {r["source_name"]} | {r["latest_source_period_end"]} | {r["days_since_latest_period"]} | {r["finality"]} |')
    lines+=['','Three impossible historical NSP ends remain unchanged and quarantined. No fact intersects an invalid boundary. Effective-history gaps, including historical HWA/KIWI, remain Unknown without retrospective backfill. I/X disagreement remains diagnostic, not a sign correction. Sparse/zero generation is not filled. Reconciliation remains revision-eligible; historical freshness does not imply a current-market or certified-final population. See the full [DQ register](data_quality_register.md).','',
      '## Refreshed analytical population','',
      '| Region | Full-year P99 NZD/MWh | Intervals | Events |','|---|---:|---:|---:|']
    for t in sorted(thresholds,key=lambda t:t['zone']):
        lines.append(f'| {t["zone"]} | {t["p99_price"]:.6f} | {t["population_intervals"]:,} | {events[t["zone"]]} |')
    lines+=['','These thresholds replace the three-month population thresholds for this release. P95, population volatility, spread, shares and event context were refreshed from the same selected year. No economic interpretation is asserted.','',
      'Thirty-day price, demand and interval-price volatility require thirty complete consecutive local dates. National has 365 daily rows and 336 full windows, starting 30 September 2025; first 29 dates expose NULL rolling values. Missing-date and missing-TP fixtures block windows. DST uses actual intervals and pooled energy/price moments. Existing seven-day products remain.','',
      '## Performance and storage','',
      f'Database after tests: {int(final_database_bytes):,} bytes, versus 6,715,307,699 before scale-up. All raw files: {int(e["raw_all_bytes"]):,} bytes, versus 125,749,268 baseline; selected release package bytes: {selected_bytes:,} (daily constituents are additionally retained). Host free after tests: {int(final_host_free):,} bytes. Both performance-time and post-test snapshots are retained. No partitioning or broad indexing was introduced.','',
      '| New reconciliation month | Successful load seconds |','|---|---:|']
    for a in sorted(attempts,key=lambda a:pubs[a['publication_id']]['source_month']):
        p=pubs[a['publication_id']]
        if p['source_name']=='reconciliation': lines.append(f'| {p["source_month"][:7]} | {float(a["elapsed_seconds"]):.3f} |')
    duration=(datetime.fromisoformat(dq['run']['completed_at'])-datetime.fromisoformat(dq['run']['started_at'])).total_seconds()
    lines += ['',f'Sum of successful new-publication load durations: {sum(float(a["elapsed_seconds"]) for a in attempts):.3f}s; excludes interruption/downtime and aborted work. Latest DQ runtime: {duration:.3f}s. Repeat analytical refresh runtimes: '+', '.join(f'{r["seconds"]:.3f}s' for r in ad['runs'])+'.','',
      '| Principal query | Measured wall seconds (EXPLAIN ANALYZE) |','|---|---:|']
    lines += [f'| {k} | {v["wall_seconds"]:.3f} |' for k,v in e['query_plans'].items()]
    lines += ['','Plans/buffers and counts are retained in outputs/scale_up/final_evidence.json; cache state and host load affect timings.','',
      '## Tests, determinism and recovery','',
      f'Full suite: **{tests["tests"]} passed**, zero failures/errors/skips, {tests["seconds"]:.3f}s. Existing 92-test preload baseline was preserved and expanded with historical-release, thirty-day, interruption-recovery and staleness tests. Original pilot exact regressions use isolated rollback-only selections; other sessions retain the committed release.','',
      f'{len(e["migrations"])} applied migration checksums match local normalised SQL. New changes were additive; earlier applied migrations were not edited. Repeat analytical input/cache/product/view hashes match, including thirty-day outputs. Selection/configuration/classification rollback fixtures still reject stale marts.','',
      'The first independent analytical validation attempt exceeded the existing container\'s 256 MiB shared-memory limit during a parallel query. Its failed stage remains recorded. The same independent SQL then passed with max_parallel_workers_per_gather=0 on that read-only validation connection. No volume recreation, data reload, formula change, migration rewrite or extra DQ/analytical refresh was needed.','',
      'Interrupted February attempt 44, March attempt 48 and July attempt 58 were recorded failed only after confirming no active loader and no committed staging/core rows; retries completed with immutable bytes. June and other committed months survived. Docker socket recovery preserved socket-only folders and restarted the existing container/volume, without data reset. Original 34 pilot analytical/DQ exports have an archive SHA manifest.','',
      'Pilot archive integrity: 34 files; zero Git-normalised SHA-256 mismatches, recorded explicitly in outputs/scale_up/archive_integrity.json.','',
      'Evidence: outputs/scale_up/final_tests.json, final_evidence.json, pilot_regression_during_load.json; outputs/data_quality/{latest_summary,determinism}.json; outputs/analytics/{validation,determinism}.json. Review the technical release before Phase 5.']
    (ROOT/'docs/phase4b_validation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Wrote validated Phase 4B technical report')

if __name__=='__main__': main()
