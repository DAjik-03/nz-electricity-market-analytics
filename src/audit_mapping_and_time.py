"""Test candidate joins and NZ time semantics against the four Phase 0 files."""
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from profile_audit_samples import ROOT, OUT, load_samples

NZ = ZoneInfo('Pacific/Auckland')


def trading_intervals(day):
    """Half-open intervals stepped in UTC between consecutive NZ local midnights."""
    start = datetime.combine(day, time(), NZ).astimezone(timezone.utc)
    stop = datetime.combine(day + timedelta(days=1), time(), NZ).astimezone(timezone.utc)
    result = []
    while start < stop:
        end = start + timedelta(minutes=30)
        local = start.astimezone(NZ)
        result.append({'trading_date': day.isoformat(), 'trading_period': len(result)+1,
            'start_utc': start.isoformat(), 'end_utc': end.isoformat(),
            'start_local': local.isoformat(), 'end_local': end.astimezone(NZ).isoformat(),
            'timezone': 'Pacific/Auckland', 'utc_offset_minutes': int(local.utcoffset().total_seconds()/60),
            'is_dst': bool(local.dst()), 'fold': local.fold})
        start = end
    return result


def position(dates, periods):
    return dates.astype('string').str.replace('-', '').astype('int64') * 100 + pd.to_numeric(periods).astype('int64')


def map_to_nsp(frame, nsp, with_network, name):
    """Assess inclusive source start/end TP boundaries without current-flag filtering."""
    frame = frame.copy().reset_index(drop=True)
    frame['audit_row_id'] = frame.index
    frame['position'] = position(frame.TradingDate, frame.TradingPeriod)
    left = ['PointOfConnection'] + (['Network'] if with_network else [])
    right = ['POC code'] + (['Network participant'] if with_network else [])
    merged = frame.merge(nsp, left_on=left, right_on=right, how='left', suffixes=('','_nsp'))
    raw_join_rows = len(merged)
    valid = merged.loc[(merged.position >= merged.valid_from) & (merged.position <= merged.valid_through)].copy()
    # Flow flags are assessed separately, not used to silently discard records.
    counts = valid.groupby('audit_row_id',observed=True).size()
    frame['nsp_matches'] = frame.audit_row_id.map(counts).fillna(0).astype(int)
    for attribute in ['Zone','Island','Network reporting region ID']:
        source = attribute + '_nsp' if attribute == 'Island' and 'Island' in frame else attribute
        groups = valid.groupby('audit_row_id',observed=True)[source]
        distinct = groups.nunique(dropna=False)
        non_null = groups.count()
        acceptable = (distinct == 1) & (non_null > 0)
        mapping = groups.first().loc[acceptable]
        frame['mapped_' + attribute] = frame.audit_row_id.map(mapping)
    metric = {'input_aggregate_rows': len(frame), 'unfiltered_left_join_rows': raw_join_rows,
        'effective_matches': len(valid), 'rows_without_nsp': int((frame.nsp_matches == 0).sum()),
        'rows_with_multiple_nsp': int((frame.nsp_matches > 1).sum()),
        'rows_with_unambiguous_zone': int(frame.mapped_Zone.notna().sum()),
        'rows_with_unambiguous_network_region': int(frame['mapped_Network reporting region ID'].notna().sum())}
    if 'source_rows' in frame:
        metric['original_source_rows'] = int(frame.source_rows.sum())
        metric['original_rows_without_nsp'] = int(frame.loc[frame.nsp_matches == 0,'source_rows'].sum())
    if 'KilowattHours' in frame:
        metric['total_kwh'] = float(frame.KilowattHours.sum())
        metric['kwh_without_nsp'] = float(frame.loc[frame.nsp_matches == 0,'KilowattHours'].sum())
        metric['kwh_without_unambiguous_zone'] = float(frame.loc[frame.mapped_Zone.isna(),'KilowattHours'].sum())
    problem = frame.loc[(frame.nsp_matches != 1) | frame.mapped_Zone.isna()]
    group = left + (['Gen_Code'] if 'Gen_Code' in frame else []) + (['FlowDirection'] if 'FlowDirection' in frame else [])
    issues = problem.groupby(group,observed=True,dropna=False).agg(observations=('audit_row_id','size'), min_matches=('nsp_matches','min'),max_matches=('nsp_matches','max'))
    if 'KilowattHours' in problem:
        issues['kwh'] = problem.groupby(group,observed=True,dropna=False).KilowattHours.sum()
    issues.reset_index().to_csv(OUT / f'{name}_mapping_exceptions.csv',index=False)
    if 'Island' in frame:
        metric['island_disagreement_rows'] = int((frame.mapped_Island.notna() & (frame.Island.astype('string') != frame.mapped_Island.astype('string'))).sum())
    if 'FlowDirection' in valid:
        mismatch = ((valid.FlowDirection == 'Offtake') & (valid['X flow'].astype('string') != '1')) | ((valid.FlowDirection == 'Injection') & (valid['I flow'].astype('string') != '1'))
        metric['nsp_flow_flag_disagreement_matches'] = int(mismatch.sum())
        flagged=valid.loc[mismatch]
        metric['nsp_flow_flag_disagreement_kwh']=float(flagged.KilowattHours.sum())
        flagged.groupby(['PointOfConnection','Network','FlowDirection'],observed=True).agg(
            observations=('audit_row_id','size'),kwh=('KilowattHours','sum')).reset_index().to_csv(OUT / f'{name}_flow_flag_disagreements.csv',index=False)
    return frame, metric, valid


def main():
    frames = load_samples()
    p,r,g = (frames[k] for k in ['prices','reconciliation','generation'])
    n = frames['nsp'].copy()
    n['valid_from'] = position(n['Start date'],n['Start TP'])
    n['valid_through'] = position(n['End date'].astype('string').fillna('9999-12-31'),n['End TP'].astype('string').fillna('50'))
    n['Network reporting region ID'] = n['Network reporting region ID'].astype('string')
    summary = {}
    pm, summary['prices_to_nsp'], _ = map_to_nsp(p,n,False,'prices')
    rcols = ['PointOfConnection','Network','Island','TradingDate','TradingPeriod','FlowDirection']
    ra = r.groupby(rcols,observed=True).agg(KilowattHours=('KilowattHours','sum'),source_rows=('KilowattHours','size')).reset_index()
    rm, summary['reconciliation_to_nsp'], _ = map_to_nsp(ra,n,True,'reconciliation')
    pkey = ['PointOfConnection','TradingDate','TradingPeriod']
    rp = ra.merge(p,on=pkey,how='left',validate='many_to_one')
    summary['reconciliation_to_prices'] = {
        'distinct_pocs': int(r.PointOfConnection.nunique()),
        'pocs_without_price': sorted(set(r.PointOfConnection)-set(p.PointOfConnection)),
        'aggregate_rows': len(rp), 'missing_price_rows': int(rp.DollarsPerMegawattHour.isna().sum()),
        'offtake_kwh': float(rp.loc[rp.FlowDirection=='Offtake','KilowattHours'].sum()),
        'offtake_kwh_without_price': float(rp.loc[(rp.FlowDirection=='Offtake') & rp.DollarsPerMegawattHour.isna(),'KilowattHours'].sum())}
    summary['reconciliation_zone_coverage_by_flow'] = rm.assign(mapped=rm.mapped_Zone.notna()).groupby(['FlowDirection','mapped'],observed=True).agg(kwh=('KilowattHours','sum'),source_rows=('source_rows','sum')).reset_index().to_dict('records')
    long = g.melt(id_vars=['Site_Code','POC_Code','Nwk_Code','Gen_Code','Fuel_Code','Tech_Code','Trading_Date'],
        value_vars=[f'TP{i}' for i in range(1,49)],var_name='tp',value_name='KilowattHours')
    long['TradingPeriod'] = long.tp.str[2:].astype(int)
    long = long.rename(columns={'POC_Code':'PointOfConnection','Nwk_Code':'Network','Trading_Date':'TradingDate'})
    gm, summary['generation_to_nsp'], gv = map_to_nsp(long,n,True,'generation')
    summary['generation_to_prices_direct'] = {'pocs_without_price': sorted(set(g.POC_Code)-set(p.PointOfConnection)),
        'kwh_at_pocs_without_price': float(long.loc[~long.PointOfConnection.isin(p.PointOfConnection),'KilowattHours'].sum())}
    # Explicitly report embedded generation routes; do not assume one-hop always reaches the grid.
    embedded = gv.loc[gv['Embedded under POC code'].notna(), ['PointOfConnection','Network','Gen_Code','Embedded under POC code','Embedded under network participant']].drop_duplicates()
    embedded.to_csv(OUT / 'generation_embedded_routes.csv',index=False)
    summary['generation_embedded_routes'] = embedded.astype('string').to_dict('records')
    routed=gv.copy()
    routed['original_poc']=routed.PointOfConnection
    routed['PointOfConnection']=routed['Embedded under POC code'].astype('string').fillna(routed.PointOfConnection.astype('string'))
    routed_prices=routed[['audit_row_id','PointOfConnection','TradingDate','TradingPeriod','KilowattHours']].merge(
        p,on=pkey,how='left',validate='many_to_one')
    summary['generation_to_prices_after_official_parent_route']={
        'input_rows':len(long),'routed_rows':len(routed_prices),
        'missing_price_rows':int(routed_prices.DollarsPerMegawattHour.isna().sum()),
        'kwh_without_price':float(routed_prices.loc[routed_prices.DollarsPerMegawattHour.isna(),'KilowattHours'].sum()),
        'limitation':'Sample requires one parent hop only; this is grid price context, not an exact plant settlement valuation.'}
    gc=g.copy()
    gc['day_kwh']=gc[[f'TP{i}' for i in range(1,49)]].sum(axis=1)
    gen_coverage=gc.groupby(['POC_Code','Nwk_Code','Gen_Code','Fuel_Code','Tech_Code'],observed=True).agg(
        days=('Trading_Date','nunique'),kwh=('day_kwh','sum'))
    gen_coverage.reset_index().to_csv(OUT / 'generation_series_coverage.csv',index=False)
    summary['generation_short_series']=gen_coverage.loc[gen_coverage.days<31].reset_index().to_dict('records')
    summary['generation_all_zero_series']=gen_coverage.loc[gen_coverage.kwh==0].reset_index().to_dict('records')
    summary['generation_fuel_technology_kwh'] = long.groupby(['Fuel_Code','Tech_Code'],observed=True).agg(rows=('KilowattHours','size'),kwh=('KilowattHours','sum')).reset_index().to_dict('records')
    # Actual source clock labels, all August records; validation against a real zone-aware calendar.
    clocks = {(row['trading_date'],row['trading_period']): row['start_local'][11:16]
        for d in sorted(r.TradingDate.unique()) for row in trading_intervals(date.fromisoformat(str(d)))}
    labels = r[['TradingDate','TradingPeriod','TradingPeriodStartTime']].drop_duplicates()
    bad_labels = sum(str(x.TradingPeriodStartTime) != clocks[(str(x.TradingDate),int(x.TradingPeriod))] for x in labels.itertuples())
    summary['time'] = {'distinct_source_clock_labels_tested':len(labels),'clock_mismatches':bad_labels,
        'sample_contains_dst_transition':False,'historical_dst_source_files_tested':False}
    example_dates = ['2024-04-07','2024-09-29','2025-04-06','2025-09-28','2026-04-05','2026-09-27','2026-08-01']
    examples = [row for d in example_dates for row in trading_intervals(date.fromisoformat(d))]
    pd.DataFrame(examples).to_csv(OUT / 'trading_period_examples.csv',index=False)
    summary['time']['calendar_example_counts'] = {d:len(trading_intervals(date.fromisoformat(d))) for d in example_dates}
    summary['nsp_validity'] = {'future_starts_after_snapshot':int((n['Start date'].astype('string') > '2026-09-10').sum()),
        'current_flag_1_future_starts':int(((n['Current flag'].astype('string')=='1') & (n['Start date'].astype('string')>'2026-09-10')).sum()),
        'invalid_reversed_intervals':int((n.valid_from>n.valid_through).sum())}
    # Within the same NSP, overlapping source validity periods are unsafe for SCD joins.
    overlaps=[]
    for code, group in n.groupby('NSP',observed=True):
        group=group.sort_values('valid_from')
        if len(group)>1:
            prior=group.valid_through.cummax().shift()
            if (group.valid_from<=prior).any(): overlaps.append(str(code))
    summary['nsp_validity']['overlapping_nsp_codes']=overlaps
    (OUT / 'mapping_and_time.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')
    print(json.dumps(summary,indent=2,default=str),flush=True)


if __name__ == '__main__':
    main()
