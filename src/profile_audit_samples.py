"""Offline sample profiling only; this is not a warehouse transformation pipeline."""
import hashlib
import json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/audit'


def load_samples():
    manifest = json.loads((OUT / 'source_manifest.json').read_text())
    if manifest['candidate_month'] != '202608' or {x['source_name'] for x in manifest['files']} != {'prices','reconciliation','generation','nsp'}:
        raise ValueError('This Phase 0 profiler is calibrated to the four August 2026 audit samples; review before changing its scope.')
    frames = {}
    for item in manifest['files']:
        path = ROOT / item['local_path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f'Checksum mismatch: {path}')
        header = pd.read_csv(path, nrows=0).columns
        numeric = {'TradingPeriod', 'DollarsPerMegawattHour', 'KilowattHours'}
        dtypes = {c: 'category' for c in header if c not in numeric and not c.startswith('TP')}
        frames[item['source_name']] = pd.read_csv(path, dtype=dtypes)
        print('Loaded', item['source_name'], frames[item['source_name']].shape, flush=True)
    return frames


def duplicate_check(frame, columns):
    return {'columns': columns, 'duplicate_rows_beyond_first': int(frame.duplicated(columns).sum()),
            'all_rows_in_duplicate_groups': int(frame.duplicated(columns, keep=False).sum())}


def describe(frame):
    return {'rows': len(frame), 'columns': len(frame.columns), 'schema': [
        {'name': c, 'parsed_dtype': str(frame[c].dtype), 'nulls': int(frame[c].isna().sum()),
         'distinct_non_null': int(frame[c].nunique()), 'examples': [str(v) for v in frame[c].dropna().unique()[:5]]}
        for c in frame.columns], 'exact_duplicates_beyond_first': int(frame.duplicated().sum())}


def main():
    frames = load_samples()
    summary = {k: describe(v) for k, v in frames.items()}
    keys = {
        'prices': [['TradingDate','TradingPeriod','PointOfConnection']],
        'reconciliation': [['TradingDate','TradingPeriod','PointOfConnection'],
            ['TradingDate','TradingPeriod','PointOfConnection','Network','Participant','FlowDirection']],
        'generation': [['Trading_Date','Gen_Code'], ['Trading_Date','POC_Code','Nwk_Code','Gen_Code'],
            ['Trading_Date','Site_Code','POC_Code','Nwk_Code','Gen_Code','Fuel_Code','Tech_Code']],
        'nsp': [['NSP'], ['NSP','Start date','Start TP'], ['POC code']],
    }
    for k, frame in frames.items():
        summary[k]['candidate_keys'] = [duplicate_check(frame, key) for key in keys[k]]
        frame.head(5).to_csv(ROOT / f'data/sample/{k}_first_5_rows.csv', index=False)
        if k != 'nsp':
            date_col = 'Trading_Date' if k == 'generation' else 'TradingDate'
            dates = pd.to_datetime(frame[date_col].astype('string'), format='%Y-%m-%d', errors='raise')
            summary[k]['date_min'] = str(dates.min().date())
            summary[k]['date_max'] = str(dates.max().date())
            summary[k]['distinct_dates'] = int(dates.nunique())
            if k != 'generation':
                summary[k]['periods_by_day'] = frame.groupby(date_col, observed=True)['TradingPeriod'].agg(['min','max','nunique']).to_dict('index')
                value_col = 'DollarsPerMegawattHour' if k == 'prices' else 'KilowattHours'
                values = frame[value_col]
                summary[k]['measure'] = {'column': value_col, 'min': float(values.min()), 'max': float(values.max()), 'sum': float(values.sum()),
                    'negative_count': int((values < 0).sum()), 'zero_count': int((values == 0).sum()), 'non_finite': int((~np.isfinite(values)).sum())}
    r = frames['reconciliation']
    summary['reconciliation']['flow_summary'] = r.groupby('FlowDirection', observed=True)['KilowattHours'].agg(['count','sum','min','max']).to_dict('index')
    summary['reconciliation']['participant_count'] = int(r.Participant.nunique())
    summary['reconciliation']['flow_values'] = [str(x) for x in r.FlowDirection.unique()]
    summary['reconciliation']['series_coverage'] = r.groupby(['PointOfConnection','Network','Participant','FlowDirection'], observed=True).size().value_counts().sort_index().to_dict()
    for source, cols in [('prices',['PointOfConnection']),('reconciliation',['PointOfConnection','Network','FlowDirection'])]:
        frame = frames[source]
        coverage = frame.drop_duplicates(cols+['TradingDate','TradingPeriod']).groupby(cols, observed=True).size()
        summary[source]['point_series_coverage'] = coverage.value_counts().sort_index().to_dict()
        coverage.rename('observed_periods').reset_index().to_csv(OUT / f'{source}_series_coverage.csv',index=False)
    g = frames['generation']
    tp = [f'TP{i}' for i in range(1,49)]
    vals = g[tp].to_numpy(dtype=float)
    summary['generation']['measure'] = {'valid_tp_cells': int(vals.size), 'nulls': int(np.isnan(vals).sum()),
        'negative_count': int((vals < 0).sum()), 'zero_count': int((vals == 0).sum()),
        'min': float(np.nanmin(vals)), 'max': float(np.nanmax(vals)), 'sum_kwh': float(np.nansum(vals))}
    summary['generation']['fuel_values'] = [str(x) for x in g.Fuel_Code.unique()]
    summary['generation']['technology_values'] = [str(x) for x in g.Tech_Code.unique()]
    series = g[['Site_Code','POC_Code','Nwk_Code','Gen_Code','Fuel_Code','Tech_Code']].drop_duplicates()
    series.to_csv(OUT / 'generation_series.csv',index=False)
    summary['generation']['distinct_series'] = len(series)
    summary['generation']['gen_codes_multiple_series'] = series.groupby('Gen_Code',observed=True).size().loc[lambda x:x>1].to_dict()
    g.loc[g.duplicated(['Trading_Date','Gen_Code'],keep=False)].to_csv(OUT / 'generation_plant_date_collisions.csv',index=False)
    n = frames['nsp']
    summary['nsp']['categorical_values'] = {c:[str(x) for x in n[c].dropna().unique()] for c in ['Current flag','Reconciliation type','Zone','Island']}
    (OUT / 'profiles.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:{x:v[x] for x in ['rows','columns','candidate_keys']} for k,v in summary.items()},indent=2))


if __name__ == '__main__':
    main()
