"""Bounded Phase 0 acquisition: one file per core source, never a historical load."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://www.emi.ea.govt.nz/Wholesale/Datasets/'
PAGES = {
    'prices': BASE + 'DispatchAndPricing/FinalEnergyPrices/ByMonth',
    'reconciliation': BASE + 'Volumes/Reconciliation/2026',
    'generation': BASE + 'Generation/Generation_MD',
    'nsp': BASE + 'MappingsAndGeospatial/NetworkSupplyPointsTable',
}


def fetch(url):
    with urlopen(url, timeout=60) as response:
        return response.read(), dict(response.headers), response.url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true', help='Restore exactly the recorded audit files; verify SHA-256.')
    args = parser.parse_args()
    evidence = ROOT / 'outputs/audit'
    evidence.mkdir(parents=True, exist_ok=True)
    manifest_path = evidence / 'source_manifest.json'
    if args.restore:
        recorded = json.loads(manifest_path.read_text())['files']
        if len(recorded) != 4 or {x['source_name'] for x in recorded} != set(PAGES):
            raise ValueError('Incomplete acquisition manifest: retain acquired files and finish acquisition before restoring a complete audit.')
        for item in recorded:
            target = ROOT / item['local_path']
            payload = target.read_bytes() if target.exists() else fetch(item['source_url'])[0]
            if hashlib.sha256(payload).hexdigest() != item['sha256']:
                raise ValueError(f"Source changed: {item['source_file_name']}; retain the old manifest and audit a new version.")
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            print('Verified', item['source_file_name'], flush=True)
        return
    if manifest_path.exists():
        raise FileExistsError('Audit already acquired. Use --restore; do not overwrite the baseline.')
    discovered = {}
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for source, page in PAGES.items():
        payload, headers, final_url = fetch(page)
        snapshot = ROOT / 'data/reference' / f'{source}_listing.html'
        snapshot.write_bytes(payload)
        tree = html.fromstring(payload)
        entries = {}
        for row in tree.xpath('//tr'):
            links = row.xpath('.//a[@href]')
            for link in links:
                href = link.get('href')
                name = href.rsplit('/', 1)[-1]
                if re.search(r'\.csv(?:\.gz)?$', name):
                    entries[name] = {'name': name, 'url': urljoin(page, href), 'listing_text': ' '.join(row.text_content().split())}
        if not entries:
            raise ValueError(f'No CSV links found: {page}')
        discovered[source] = {'page': page, 'retrieved_at_utc': retrieved_at, 'listing_sha256': hashlib.sha256(payload).hexdigest(), 'files': sorted(entries.values(), key=lambda x: x['name'])}
        print('Listed', source, len(entries), flush=True)
    period_sets = []
    for source in ['prices', 'reconciliation', 'generation']:
        periods = set()
        for item in discovered[source]['files']:
            if 'incomplete' in item['name'] or '_I.' in item['name']:
                continue
            match = re.search(r'(20\d{4})', item['name'])
            if match:
                periods.add(match[1])
        period_sets.append(periods)
    common = max(set.intersection(*period_sets))
    discovered['latest_common_published_month_candidate'] = common
    discovered['scope_note'] = 'Phase 0 snapshot; reconciliation listing is bounded to 2026. Availability is not completeness or finality.'
    (evidence / 'source_discovery.json').write_text(json.dumps(discovered, indent=2), encoding='utf-8')
    manifest = {'audit_retrieved_at_utc': retrieved_at, 'candidate_month': common, 'files': []}
    for source in PAGES:
        choices = discovered[source]['files']
        if source != 'nsp':
            choices = [x for x in choices if common in x['name'] and 'incomplete' not in x['name']]
        choice = max(choices, key=lambda x: x['name'])
        payload, headers, final_url = fetch(choice['url'])
        if source == 'reconciliation':
            if payload[:2] != b'\x1f\x8b':
                raise ValueError('Expected a gzip reconciliation file')
        elif b'<html' in payload[:500].lower():
            raise ValueError('Received HTML instead of CSV')
        checksum = hashlib.sha256(payload).hexdigest()
        target = ROOT / 'data/raw' / source / checksum / choice['name']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        prepared = re.search(r'_(\d{8})_(\d{6})\.csv', choice['name'])
        manifest['files'].append({
            'source_name': source, 'source_file_name': choice['name'], 'source_url': choice['url'],
            'resolved_url': final_url, 'source_period': common if source != 'nsp' else None,
            'source_snapshot_date': choice['name'][:8] if source == 'nsp' else None,
            'source_modified_at': headers.get('Last-Modified'), 'etag': headers.get('ETag'),
            'source_prepared_at_unzoned': datetime.strptime(''.join(prepared.groups()), '%Y%m%d%H%M%S').isoformat() if prepared else None,
            'source_version': '_'.join(prepared.groups()) if prepared else checksum,
            'downloaded_at_utc': datetime.now(timezone.utc).isoformat(), 'file_size_bytes': len(payload),
            'sha256': checksum, 'local_path': target.relative_to(ROOT).as_posix(),
            'ingestion_status': 'downloaded_for_audit_not_loaded',
            'revision_status': 'revision_eligible_not_final' if source == 'reconciliation' else 'snapshot_not_assumed_immutable',
            'listing_text': choice['listing_text'],
        })
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print('Acquired', source, len(payload), choice['name'], flush=True)


if __name__ == '__main__':
    main()
