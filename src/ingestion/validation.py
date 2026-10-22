"""Full-file pilot validation with deterministic, version-linked evidence."""
import gc
import hashlib
import json
import logging
import platform
from importlib.metadata import version as package_version
from pathlib import Path
import pandas as pd
from .acquisition import digest, verify_version, write_json
from .intervals import month_calendar
from .mapping import map_effective
from .parsers import parse_month, parse_nsp
from .revisions import reconciliation_delta

LOG = logging.getLogger(__name__)


def code_fingerprint():
    paths = sorted(Path(__file__).parent.glob('*.py')) + [Path(__file__).resolve().parents[2] / 'config/source_schema.json']
    return digest(b''.join(p.name.encode() + p.read_bytes().replace(b'\r\n', b'\n') for p in paths))


def persist_frame(root, target, frame):
    """Content-hashed derived file, separate from immutable publisher bytes."""
    target.parent.mkdir(parents=True, exist_ok=True)
    sidecar = target.with_suffix(target.suffix + '.json')
    if target.exists():
        if not sidecar.exists():
            raise ValueError(f'Derived file lacks integrity metadata: {target}')
        previous = json.loads(sidecar.read_text())
        if digest(target.read_bytes()) != previous['sha256'] or previous['rows'] != len(frame):
            raise ValueError(f'Derived file integrity check failed: {target}')
        return previous
    if not target.exists():
        temporary = target.with_suffix('.tmp')
        frame.to_csv(temporary, index=False, compression={'method': 'gzip', 'compresslevel': 1, 'mtime': 0})
        temporary.replace(target)
    metadata = dict(path=target.relative_to(root).as_posix(), sha256=digest(target.read_bytes()), rows=len(frame))
    write_json(sidecar, metadata)
    return metadata


def fd_violations(frame, determinants, dependent):
    counts = frame.groupby(determinants, observed=True, dropna=False)[dependent].nunique(dropna=False)
    return int((counts > 1).sum())


def validate_pilot(root, config, manifest):
    evidence = root / config['evidence_directory']
    fingerprint = code_fingerprint()
    chosen = {key: manifest['versions'][vid] for key, vid in manifest['selected'].items()}
    result_path = evidence / 'validation.json'
    runtime = {'python': platform.python_version(), **{p: package_version(p) for p in ['pandas', 'numpy', 'lxml', 'tzdata', 'PyYAML']}}
    cache_key = digest(json.dumps(dict(selected=manifest['selected'], config=config, code=fingerprint, runtime=runtime), sort_keys=True).encode())
    if result_path.exists():
        old = json.loads(result_path.read_text())
        if old.get('cache_key') == cache_key:
            missing = False
            for artefact in old['artefacts']:
                if not (root / artefact['path']).exists():
                    missing = True
                    continue
                if digest((root / artefact['path']).read_bytes()) != artefact['sha256']:
                    raise ValueError(f'Derived artefact corrupted: {artefact["path"]}')
            if not missing:
                LOG.info('Validated pinned raw and derived hashes; unchanged pilot outputs reused')
                return old
    result = dict(cache_key=cache_key, code_sha256=fingerprint, runtime=runtime, selected_versions=manifest['selected'], months={}, artefacts=[])
    nsp_version = chosen['nsp/snapshot']
    nsp, result['nsp'] = parse_nsp(verify_version(root, nsp_version))
    result['nsp']['sha256'] = nsp_version['sha256']
    result['nsp']['mapping_basis'] = 'Pinned 2026-09-10 snapshot applied to historical effective date/TP; not contemporaneous as-known reporting.'
    stage = root / config['staging_directory'] / digest((fingerprint + json.dumps(runtime, sort_keys=True)).encode())
    result['artefacts'].append(persist_frame(root, stage / nsp_version['sha256'] / 'nsp.csv.gz', nsp))
    plant_attributes, volume_attributes = [], []
    for month in config['pilot_months']:
        LOG.info('Validating month %s', month)
        monthly = result['months'][month] = {}
        calendar = month_calendar(month)
        result['artefacts'].append(persist_frame(root, stage / f'intervals_{month}.csv.gz', calendar))
        # Retain only prices plus the current large fact in memory.
        price_version = chosen['prices/' + month]
        prices, monthly['prices'] = parse_month(verify_version(root, price_version), 'prices', month)
        result['artefacts'].append(persist_frame(root, stage / price_version['sha256'] / 'prices.csv.gz', prices))
        mapped, monthly['prices']['mapping'] = map_effective(prices, nsp, False)
        del mapped
        price_key = ['TradingDate', 'TradingPeriod', 'PointOfConnection']
        price_identity = prices[price_key]
        for source in ['reconciliation', 'generation']:
            LOG.info('Parsing %s %s', source, month)
            version = chosen[source + '/' + month]
            frame, report = parse_month(verify_version(root, version), source, month)
            monthly[source] = report
            report['source_sha256'] = version['sha256']
            result['artefacts'].append(persist_frame(root, stage / version['sha256'] / f'{source}.csv.gz', frame))
            if source == 'reconciliation':
                previous_versions = [v for v in manifest['versions'].values() if v['source'] == source and v['month'] == month and v['sha256'] != version['sha256']]
                report['revision_comparisons'] = []
                for previous_version in previous_versions:
                    previous, _ = parse_month(verify_version(root, previous_version), source, month)
                    report['revision_comparisons'].append(dict(previous_sha256=previous_version['sha256'], current_sha256=version['sha256'],
                        **reconciliation_delta(previous, frame)))
                    del previous
                report['observed_distinct_content_versions'] = len({v['sha256'] for v in manifest['versions'].values() if v['source'] == source and v['month'] == month})
                groups = ['TradingDate', 'TradingPeriod', 'PointOfConnection', 'Network', 'Island', 'FlowDirection']
                aggregate = frame.groupby(groups, observed=True).agg(KilowattHours=('KilowattHours', 'sum'), source_rows=('KilowattHours', 'size')).reset_index()
                volume_attributes.append(frame[['PointOfConnection', 'Network', 'Island']].drop_duplicates().astype(str))
                report['flows'] = frame.groupby('FlowDirection', observed=True).KilowattHours.agg(['size', 'sum']).reset_index().astype(object).to_dict('records')
            else:
                aggregate = frame
                plant_attributes.append(frame[['Gen_Code', 'PointOfConnection', 'Network', 'Site_Code', 'Fuel_Code', 'Tech_Code']].drop_duplicates().astype(str))
                storage = frame.Fuel_Code.astype(str).eq('ELE') | frame.Tech_Code.astype(str).eq('BAT')
                report['storage'] = dict(rows=int(storage.sum()), kwh=float(frame.loc[storage, 'KilowattHours'].sum()),
                    classifications=frame.loc[storage, ['Gen_Code', 'Fuel_Code', 'Tech_Code']].drop_duplicates().astype(str).to_dict('records'),
                    interpretation='Retain electricity/battery as storage, not primary renewable generation; no charging or round-trip efficiency inferred.')
            LOG.info('Mapping %s %s', source, month)
            mapped, report['mapping'] = map_effective(aggregate, nsp, True)
            matches = aggregate.merge(price_identity, on=price_key, how='left', indicator=True, validate='many_to_one')
            missing = matches['_merge'] == 'left_only'
            report['direct_price_coverage'] = dict(rows=len(matches), unmatched_rows=int(missing.sum()),
                unmatched_kwh=float(matches.loc[missing, 'KilowattHours'].sum()),
                unmatched_pocs=sorted(str(x) for x in matches.loc[missing, 'PointOfConnection'].unique()))
            if source == 'generation':
                report['functional_dependencies'] = {f'Gen_Code -> {c}': fd_violations(frame, ['Gen_Code'], c) for c in ['PointOfConnection', 'Network', 'Site_Code', 'Fuel_Code', 'Tech_Code']}
            del mapped, matches, aggregate, frame
            gc.collect()
        monthly['eligibility'] = dict(file_availability=True,
            date_tp_complete=all(not monthly[s]['calendar']['missing_intervals'] for s in ['prices', 'reconciliation', 'generation']),
            sparse_activity_is_not_file_incompleteness=True,
            revision_finality='not_final: reconciliation is revision-eligible; current observed versions only',
            mapping_policy='Unknown retained and measured; not an eligibility veto',
            price_node_continuity=monthly['prices']['node_calendar']['internal_missing_intervals'] == 0,
            local_time_labels_consistent=monthly['reconciliation']['local_start_time_validation']['mismatched_rows'] == 0,
            eligible_for_versioned_pilot=all(not monthly[s]['calendar']['missing_intervals'] for s in ['prices', 'reconciliation', 'generation']) and monthly['reconciliation']['local_start_time_validation']['mismatched_rows'] == 0 and monthly['prices']['node_calendar']['internal_missing_intervals'] == 0)
        del prices
        write_json(evidence / f'validation_{month}.json', monthly)
    plants = pd.concat(plant_attributes).drop_duplicates()
    volumes = pd.concat(volume_attributes).drop_duplicates()
    result['historical_functional_dependencies'] = {
        'generation': {f'Gen_Code -> {c}': fd_violations(plants, ['Gen_Code'], c) for c in ['PointOfConnection', 'Network', 'Site_Code', 'Fuel_Code', 'Tech_Code']},
        'generation_connection': {f'Gen_Code,POC,network -> {c}': fd_violations(plants, ['Gen_Code', 'PointOfConnection', 'Network'], c) for c in ['Site_Code', 'Fuel_Code', 'Tech_Code']},
        'reconciliation_POC_network_to_Island': fd_violations(volumes, ['PointOfConnection', 'Network'], 'Island'),
        'cross_month_keys': 'All selected files pass their natural keys; disjoint, strictly checked trading months make cross-month fact-key collisions impossible. Source versions are selected, never unioned.'}
    result['artefacts'].append(persist_frame(root, stage / 'generation_attributes.csv.gz', plants))
    result['source_version_comparison_to_phase0'] = []
    baseline = json.loads((root / 'outputs/audit/source_manifest.json').read_text())
    for old in baseline['files']:
        observed = [x for x in chosen.values() if x['filename'] == old['source_file_name']]
        for new in observed:
            result['source_version_comparison_to_phase0'].append(dict(filename=new['filename'], same_sha256=new['sha256'] == old['sha256'],
                prior_sha256=old['sha256'], current_sha256=new['sha256'], prior_http_modified=old['source_modified_at'], current_http_modified=new['http_last_modified']))
    write_json(result_path, result)
    LOG.info('Pilot validation complete: %s', result_path)
    return result
