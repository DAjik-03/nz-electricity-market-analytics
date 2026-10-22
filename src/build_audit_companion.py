"""Build the Phase 0 field dictionary and execute a small inspectable notebook."""
import contextlib
import importlib.metadata
import io
import json
import platform
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/audit'

DESCRIPTIONS={
    'TradingDate':'Local NZ trading date, ISO YYYY-MM-DD.',
    'Trading_Date':'Local NZ trading date, ISO YYYY-MM-DD.',
    'TradingPeriod':'Consecutive half-hour period number for the local date; 1–46/48/50.',
    'PointOfConnection':'Full grid point-of-connection code; preserve as text.',
    'DollarsPerMegawattHour':'Final energy price in NZD/MWh; retain zero, negative and extreme values when present.',
    'Network':'Network code; part of the reconciled-volume natural key.',
    'Island':'Source island code NI or SI; retain and compare with mapping source.',
    'Participant':'Reconciliation participant code, distinct from network.',
    'TradingPeriodStartTime':'Local HH:MM start label; no date or timezone offset; not a unique instant.',
    'FlowDirection':'Observed Offtake or Injection; separate measures, not additive demand.',
    'KilowattHours':'Loss-adjusted reconciled energy for the interval in kWh.',
    'Site_Code':'Source geographic site code; retain it, never use a three-letter match as a substitute for a verified POC join.',
    'POC_Code':'Generation point of connection; may be embedded under another pricing connection.',
    'Nwk_Code':'Generation network code; part of tested connection identity.',
    'Gen_Code':'Source plant name/code, including Unicode; multiple connection series can share it.',
    'Fuel_Code':'Source fuel label; mixed aliases observed; classification must be explicit.',
    'Tech_Code':'Source technology label; preserve separately from fuel.',
    'Current flag':'Source current-record indicator; not proof of validity at an observation date.',
    'NSP':'Network supply point identifier; repeats across effective versions.',
    'NSP replaced by':'Source successor NSP reference; not an automatic historical rewrite instruction.',
    'POC code':'Full connection code of this NSP version.',
    'Network participant':'Network participant for this NSP version.',
    'Embedded under POC code':'Official parent connection for an embedded NSP, if present.',
    'Embedded under network participant':'Parent connection network participant, if present.',
    'Reconciliation type':'Observed GN, EN, NP, GG or GD; preserve code, do not infer missing meanings.',
    'X flow':'Source offtake flow flag; observed reconciliation disagreements require investigation.',
    'I flow':'Source injection flow flag; not used as a row-deletion filter.',
    'Description':'Source location/NSP description.',
    'NZTM easting':'Source NZTM easting, not longitude; verify CRS and conversion before mapping.',
    'NZTM northing':'Source NZTM northing, not latitude; verify CRS and conversion before mapping.',
    'Network reporting region ID':'Official network reporting region identifier; not a regional council code.',
    'Network reporting region':'Network reporting region label; separate from market Zone.',
    'Zone':'Source pricing/market Zone: UNI, CNI, LNI, USI, LSI; null remains Unknown.',
    'Start date':'Effective start date; combine with Start TP.',
    'Start TP':'Effective starting trading period on Start date.',
    'End date':'Effective final date when present; null treated as open-ended in this audit.',
    'End TP':'Effective final trading period; inclusive convention is an audit assumption supported by adjacent rows.',
    'SB ICP':'Source ICP reference; retain as text; operational role not needed for Phase 0 joins.',
    'Balancing code':'Source balancing reference code; retain without assuming analytical identity.',
    'MEP':'Source metering equipment provider code; optional metadata.',
    'Responsible participant':'Source responsible participant code; optional metadata, not the fact Participant.',
    'Certification expiry':'Source metering certification expiry date; not NSP mapping validity.',
    'Metering information exemption expiry date':'Source exemption expiry date; not NSP mapping validity.',
}


def field_type(name):
    if name in {'TradingPeriod','Start TP','End TP'}: return 'smallint'
    if name in {'Current flag','X flow','I flow'}: return 'smallint / validated boolean'
    if name in {'DollarsPerMegawattHour','KilowattHours','NZTM easting','NZTM northing'} or name.startswith('TP'): return 'numeric'
    if name in {'TradingDate','Trading_Date','Start date','End date','Certification expiry','Metering information exemption expiry date'}: return 'date'
    return 'text'


def main():
    profiles=json.loads((OUT/'profiles.json').read_text())
    lines=['# Actual source field dictionary','',
        'August 2026 fact samples and the 10 September 2026 NSP snapshot. Types below are recommended PostgreSQL staging types after validated parsing; raw source text remains unchanged. Pandas categorical encodings in profiles.json are memory optimisation, not source types. Null counts describe the retained sample only.','']
    for source,profile in profiles.items():
        lines += [f'## {source.title()}', '',f"{profile['rows']:,} rows, {profile['columns']} columns.",'',
                  '| Source field | Suggested type | Nulls | Distinct populated values | Meaning / treatment |',
                  '|---|---|---:|---:|---|']
        for col in profile['schema']:
            name=col['name']
            description=(f'Energy in kWh in trading period {name[2:]}; structural null if that TP does not exist on the date.'
                         if name.startswith('TP') else DESCRIPTIONS[name])
            lines.append(f"| {name} | {field_type(name)} | {col['nulls']:,} | {col['distinct_non_null']:,} | {description} |")
        lines += ['']
    (ROOT/'docs/data_dictionary.md').write_text('\n'.join(lines),encoding='utf-8')
    env={'python':platform.python_version(),'platform':platform.platform(),
         'packages':{x:importlib.metadata.version(x) for x in ['pandas','numpy','lxml','tzdata']}}
    (OUT/'environment.json').write_text(json.dumps(env,indent=2),encoding='utf-8')
    markdown='''# Phase 0 source audit companion

This executed notebook checks the retained four-file audit snapshot. It is not a production ingestion pipeline or a market findings report. Run from the project root or notebooks directory after restoring the files in outputs/audit/source_manifest.json. See docs/source_audit.md for interpretation and limits.

The complete effective-date mapping logic is in src/audit_mapping_and_time.py; the final cell reruns it. Source DST rows are not covered by the August sample. The notebook's captured outputs were produced by executing each code cell in a shared Python namespace; no notebook service is required.
'''
    codes=[
        "from pathlib import Path\nimport sys, json, hashlib\nroot = Path.cwd()\nif not (root / 'PROGRESS.md').exists():\n    root = root.parent\nassert (root / 'PROGRESS.md').exists(), 'Run from project root or notebooks/'\nsys.path.insert(0, str(root / 'src'))\nfrom profile_audit_samples import load_samples, duplicate_check\nfrom audit_mapping_and_time import trading_intervals\nfrom datetime import date\nframes = load_samples()\nprint({k: v.shape for k, v in frames.items()})",
        "keys = {'prices':['TradingDate','TradingPeriod','PointOfConnection'], 'reconciliation':['TradingDate','TradingPeriod','PointOfConnection','Network','Participant','FlowDirection'], 'generation':['Trading_Date','POC_Code','Nwk_Code','Gen_Code'], 'nsp':['NSP','Start date','Start TP']}\nfor source, columns in keys.items():\n    assert not frames[source][columns].isna().any().any()\n    result = duplicate_check(frames[source], columns)\n    assert result['duplicate_rows_beyond_first'] == 0\n    print(source, result)\nprint('Plant/date collisions:', duplicate_check(frames['generation'], ['Trading_Date','Gen_Code']))",
        "r, p = frames['reconciliation'], frames['prices']\nkey = ['PointOfConnection','TradingDate','TradingPeriod']\nofftake = r.loc[r.FlowDirection == 'Offtake'].groupby(key, observed=True).KilowattHours.sum().reset_index()\njoined = offtake.merge(p, on=key, how='left', validate='one_to_one')\nassert len(joined) == len(offtake)\nassert joined.DollarsPerMegawattHour.notna().all()\nassert joined.KilowattHours.sum() == offtake.KilowattHours.sum()\nprint('Observed offtake kWh with unique matching price:', joined.KilowattHours.sum())\nprint('Unmatched price rows:', joined.DollarsPerMegawattHour.isna().sum())",
        "for day, expected in [('2026-04-05',50),('2026-09-27',46),('2026-08-01',48)]:\n    intervals=trading_intervals(date.fromisoformat(day))\n    assert len(intervals)==expected\n    print(day, len(intervals), 'TP5:', intervals[4]['start_local'])\ng=frames['generation']\nassert g[['TP49','TP50']].isna().all().all()\nassert g[[f'TP{i}' for i in range(1,49)]].notna().all().all()\nprint('August padding and populated period checks passed; actual DST market files remain untested.')",
        "# Release large frames before the complete effective-date audit reloads them.\ndel frames, r, p, g, offtake, joined\nimport gc\ngc.collect()\nfrom audit_mapping_and_time import main as run_mapping_audit\nrun_mapping_audit()",
    ]
    cells=[{'cell_type':'markdown','id':'audit-context','metadata':{},'source':markdown.splitlines(True)}]
    namespace={}
    for index,code in enumerate(codes,1):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(compile(code,f'audit-cell-{index}','exec'),namespace)
        cells.append({'cell_type':'code','id':f'audit-check-{index}','metadata':{},'execution_count':index,
            'source':code.splitlines(True),'outputs':[{'output_type':'stream','name':'stdout','text':output.getvalue().splitlines(True)}]})
        print(f'Executed notebook cell {index}/{len(codes)}',flush=True)
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
        'language_info':{'name':'python','version':platform.python_version()}},'cells':cells}
    (ROOT/'notebooks/source_audit.ipynb').write_text(json.dumps(notebook,indent=2,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':
    main()
