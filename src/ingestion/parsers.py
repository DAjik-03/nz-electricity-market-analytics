"""Strict source contracts. Raw classifications and identifiers are retained."""
import csv
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .intervals import boundary, day_intervals, month_calendar

CONTRACT = Path(__file__).resolve().parents[2] / 'config/source_schema.json'
KEYS = {
    'prices': ['TradingDate', 'TradingPeriod', 'PointOfConnection'],
    'reconciliation': ['TradingDate', 'TradingPeriod', 'PointOfConnection', 'Network', 'Participant', 'FlowDirection'],
    'generation': ['TradingDate', 'TradingPeriod', 'Gen_Code', 'PointOfConnection', 'Network'],
    'nsp': ['NSP', 'Start date', 'Start TP'],
}


def read_source(path, source):
    expected = json.loads(CONTRACT.read_text())[source]
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        header = next(csv.reader(stream))
    if len(header) != len(set(header)) or set(header) != set(expected):
        raise ValueError(f'Schema drift in {source}: missing={sorted(set(expected)-set(header))}, added={sorted(set(header)-set(expected))}, duplicate_headers={len(header)!=len(set(header))}')
    numeric = {'TradingPeriod', 'DollarsPerMegawattHour', 'KilowattHours'} | {f'TP{i}' for i in range(1, 51)}
    # Only an empty CSV field is null; e.g. identifier NA must not disappear.
    frame = pd.read_csv(path, dtype={c: 'float64' if c in numeric else 'category' for c in header},
                        keep_default_na=False, na_values=[''], encoding='utf-8-sig')
    if frame.empty:
        raise ValueError(f'Empty source: {source}')
    return frame, dict(columns=header, missing=[], added=[], reordered=header != expected)


def required(frame, columns):
    missing = {c: int(frame[c].isna().sum()) for c in columns if frame[c].isna().any()}
    if missing:
        raise ValueError(f'Null required values: {missing}')


def check_key(frame, source):
    key = KEYS[source]
    required(frame, key)
    duplicates = int(frame.duplicated(key).sum())
    if duplicates:
        raise ValueError(f'{source} natural-key collision: {duplicates}; key={key}')
    return dict(columns=key, rows=len(frame), duplicates=duplicates)


def attach_intervals(frame, month):
    required(frame, ['TradingDate', 'TradingPeriod'])
    dates = frame.TradingDate.astype('string')
    # Exact source date syntax, not permissive locale inference.
    if not dates.str.fullmatch(r'\d{4}-\d{2}-\d{2}').all() or not dates.str.startswith(month).all():
        raise ValueError(f'Unexpected date format or month outside {month}')
    pd.to_datetime(dates.drop_duplicates(), format='%Y-%m-%d', errors='raise')
    tp = frame.TradingPeriod
    if not np.isfinite(tp).all() or not (tp == np.floor(tp)).all():
        raise ValueError('Non-integral trading period')
    frame['TradingPeriod'] = tp.astype('int16')
    calendar = month_calendar(month)
    lookups = {(r.TradingDate, r.TradingPeriod): r.interval_start_utc for r in calendar.itertuples()}
    # A small categorical mapping avoids replicating twelve calendar fields over
    # millions of volume rows. The full interval dimension is a separate artefact.
    codes = dates.str[-2:].astype('int16') * 100 + frame.TradingPeriod
    lookup = {int(d[-2:])*100 + p: v for (d, p), v in lookups.items()}
    frame['interval_start_utc'] = codes.map(lookup).astype('category')
    if frame.interval_start_utc.isna().any():
        raise ValueError('Trading period outside actual NZ day (46/48/50)')
    observed = set(zip(frame.TradingDate.astype(str), frame.TradingPeriod))
    missing = sorted(set(lookups) - observed)
    return frame, dict(expected_intervals=len(calendar), observed_intervals=len(observed), missing_intervals=[list(x) for x in missing])


def parse_month(path, source, month):
    raw, schema = read_source(path, source)
    report = dict(source_rows=len(raw), schema=schema)
    if source == 'generation':
        ids = ['Site_Code', 'POC_Code', 'Nwk_Code', 'Gen_Code', 'Fuel_Code', 'Tech_Code', 'Trading_Date']
        required(raw, ids)
        long = raw.melt(id_vars=ids, value_vars=[f'TP{i}' for i in range(1, 51)], var_name='source_tp', value_name='KilowattHours')
        long['TradingPeriod'] = long.source_tp.str[2:].astype('int16')
        long = long.rename(columns={'Trading_Date': 'TradingDate', 'POC_Code': 'PointOfConnection', 'Nwk_Code': 'Network'})
        limits = {d: len(day_intervals(str(d))) for d in long.TradingDate.unique()}
        padding = long.TradingPeriod > long.TradingDate.astype(str).map(limits)
        if long.loc[padding, 'KilowattHours'].notna().any():
            raise ValueError('Generation has non-null data in a structural DST padding column')
        report['structural_padding_cells'] = int(padding.sum())
        report['valid_interval_null_cells'] = int(long.loc[~padding, 'KilowattHours'].isna().sum())
        if report['valid_interval_null_cells']:
            raise ValueError('Generation has null data in a valid trading interval')
        frame = long.loc[~padding].drop(columns=['source_tp']).copy()
        for c in ids[:1] + ['PointOfConnection', 'Network', 'Gen_Code', 'Fuel_Code', 'Tech_Code', 'TradingDate']:
            frame[c] = frame[c].astype('category')
        series = raw.groupby(['Gen_Code', 'POC_Code', 'Nwk_Code', 'Fuel_Code', 'Tech_Code'], observed=True).Trading_Date.nunique()
        days = len(month_calendar(month).TradingDate.unique())
        report['series_days'] = {'series': len(series), 'short_series': int((series < days).sum()),
            'details': series.reset_index(name='observed_days').astype(object).to_dict('records')}
        report['fuel_codes'] = sorted(str(x) for x in raw.Fuel_Code.unique())
        report['technology_codes'] = sorted(str(x) for x in raw.Tech_Code.unique())
        report['fuel_technology_pairs'] = raw[['Fuel_Code', 'Tech_Code']].drop_duplicates().astype(str).sort_values(['Fuel_Code', 'Tech_Code']).to_dict('records')
    else:
        frame = raw
    measure = 'DollarsPerMegawattHour' if source == 'prices' else 'KilowattHours'
    required(frame, [measure])
    if not np.isfinite(frame[measure]).all():
        raise ValueError('Non-finite source measure')
    if source == 'reconciliation' and not set(frame.FlowDirection.unique()) <= {'Injection', 'Offtake'}:
        raise ValueError('Unexpected reconciliation flow direction')
    frame, report['calendar'] = attach_intervals(frame, month)
    report['natural_key'] = check_key(frame, source)
    if source == 'prices':
        counts = frame.groupby('PointOfConnection', observed=True).agg(rows=('TradingPeriod', 'size'),
            first=('interval_start_utc', lambda x: min(x.astype(str))), last=('interval_start_utc', lambda x: max(x.astype(str))))
        counts['internal_missing_intervals'] = ((pd.to_datetime(counts['last']) - pd.to_datetime(counts['first'])).dt.total_seconds()/1800 + 1 - counts['rows']).astype(int)
        report['node_calendar'] = dict(nodes=len(counts), internal_missing_intervals=int(counts.internal_missing_intervals.sum()),
            partial_month_nodes=counts.loc[counts.rows != report['calendar']['expected_intervals']].reset_index().astype(object).to_dict('records'),
            note='Check continuity between each node first/last observed interval; partial edge activity is reported, not filled.')
    report['measure'] = dict(column=measure, sum=float(frame[measure].sum()), min=float(frame[measure].min()), max=float(frame[measure].max()),
        zero_rows=int((frame[measure] == 0).sum()), negative_rows=int((frame[measure] < 0).sum()))
    report['dst_days'] = []
    for day in sorted(frame.TradingDate.unique()):
        intervals = day_intervals(str(day))
        if len(intervals) == 48:
            continue
        sample = frame.loc[frame.TradingDate == day]
        entity = [c for c in KEYS[source] if c not in ['TradingDate', 'TradingPeriod']]
        counts = sample.groupby(entity, observed=True).TradingPeriod.nunique()
        report['dst_days'].append(dict(date=str(day), expected_periods=len(intervals), observed_periods=sorted(int(x) for x in sample.TradingPeriod.unique()),
            rows=len(sample), active_series=len(counts), series_with_all_periods=int((counts == len(intervals)).sum()),
            sparse_series=int((counts != len(intervals)).sum()),
            actual_rows=sample.loc[sample.TradingPeriod.isin([4, 5, 6, 7, len(intervals)])].groupby('TradingPeriod', observed=True).head(1).astype(str).to_dict('records')))
    if source == 'reconciliation':
        required(frame, ['TradingPeriodStartTime', 'Island'])
        expected = frame.interval_start_utc.astype(str).map({r['interval_start_utc']: r['local_start'][11:16] for d in sorted(frame.TradingDate.unique()) for r in day_intervals(str(d))})
        actual = frame.TradingPeriodStartTime.astype(str)
        mismatch = actual != expected
        report['local_start_time_validation'] = dict(mismatched_rows=int(mismatch.sum()),
            examples=frame.loc[mismatch, ['TradingDate', 'TradingPeriod', 'TradingPeriodStartTime', 'interval_start_utc']].drop_duplicates().head(10).astype(str).to_dict('records'))
    return frame, report


def parse_nsp(path):
    frame, schema = read_source(path, 'nsp')
    required(frame, ['NSP', 'POC code', 'Network participant', 'Start date', 'Start TP'])
    report = dict(schema=schema, natural_key=check_key(frame, 'nsp'))
    starts, ends, errors = [], [], []
    for row in frame.to_dict('records'):
        try:
            start = boundary(row['Start date'], row['Start TP'])
            if pd.isna(row['End date']) != pd.isna(row['End TP']):
                raise ValueError('Partially null end boundary')
            end = None if pd.isna(row['End date']) else boundary(row['End date'], row['End TP'], end=True)
            if end is not None and end <= start:
                raise ValueError('End boundary precedes start')
        except ValueError as error:
            errors.append(dict(NSP=str(row['NSP']), start_date=str(row['Start date']), start_tp=str(row['Start TP']),
                end_date=str(row['End date']), end_tp=str(row['End TP']), error=str(error)))
            start, end = None, None
        starts.append(start)
        ends.append(end)
    report['invalid_boundaries'] = errors
    frame['effective_start_utc'] = starts
    frame['effective_end_utc_exclusive'] = ends
    frame['boundary_valid'] = frame.effective_start_utc.notna()
    # Preserve source inclusive positions even when an old source TP is invalid
    # for its civil date. Never reinterpret that invalid end as open-ended.
    frame['source_start_position'] = frame['Start date'].astype(str).str.replace('-', '').astype('int64') * 100 + pd.to_numeric(frame['Start TP']).astype('int64')
    frame['source_end_position'] = frame['End date'].astype('string').fillna('9999-12-31').str.replace('-', '').astype('int64') * 100 + pd.to_numeric(frame['End TP']).fillna(50).astype('int64')
    if (frame.source_end_position < frame.source_start_position).any():
        raise ValueError('NSP inclusive source range is reversed')
    all_ordered = frame.sort_values(['NSP', 'source_start_position'])
    next_source_start = all_ordered.groupby('NSP', observed=True).source_start_position.shift(-1)
    report['inclusive_source_overlaps'] = int((all_ordered.source_end_position >= next_source_start).sum())
    if report['inclusive_source_overlaps']:
        raise ValueError('Overlapping inclusive NSP source histories')
    ordered = frame.loc[frame.boundary_valid].sort_values(['NSP', 'effective_start_utc']).copy()
    ordered['next_start_utc'] = ordered.groupby('NSP', observed=True).effective_start_utc.shift(-1)
    pairs = ordered.loc[ordered.next_start_utc.notna()].copy()
    pairs['adjacent'] = pairs.effective_end_utc_exclusive == pairs.next_start_utc
    overlap = pairs.effective_end_utc_exclusive.isna() | (pairs.effective_end_utc_exclusive > pairs.next_start_utc)
    report['transition_pairs'] = len(pairs)
    report['adjacent_pairs'] = int(pairs.adjacent.sum())
    report['gap_pairs'] = int((~pairs.adjacent & ~overlap).sum())
    report['overlap_pairs'] = int(overlap.sum())
    report['intraday_adjacent_pairs'] = int((pairs.adjacent & (pd.to_numeric(pairs['End TP']) < pairs['End date'].astype(str).map(lambda d: len(day_intervals(d))))).sum())
    report['intraday_transition_examples'] = pairs.loc[pairs.adjacent & (pd.to_numeric(pairs['End TP']) < 46),
        ['NSP', 'End date', 'End TP', 'effective_end_utc_exclusive', 'next_start_utc']].head(5).astype(str).to_dict('records')
    report['transition_examples'] = pairs.loc[pairs.adjacent, ['NSP', 'End date', 'End TP', 'effective_end_utc_exclusive', 'next_start_utc']].head(10).astype(str).to_dict('records')
    if overlap.any():
        raise ValueError('Overlapping effective NSP histories')
    return frame, report
