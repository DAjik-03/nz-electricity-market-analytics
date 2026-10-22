"""Discovery and immutable storage. A failed refresh never changes a selection."""
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, unquote
from urllib.request import urlopen

import yaml
from lxml import html

LOG = logging.getLogger(__name__)
PATTERNS = {
    'prices': r'^(\d{6})_FinalEnergyPrices\.csv$',
    'generation': r'^(\d{6})_Generation_MD\.csv$',
    'reconciliation': r'^ReconciledInjectionAndOfftake_(\d{6})_(\d{8})_(\d{6})\.csv\.gz$',
    'nsp': r'^(\d{8})_NetworkSupplyPointsTable\.csv$',
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write_json(path, value):
    """Atomic replace; identical evidence is not rewritten."""
    path = Path(path)
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def load_config(path):
    config = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    months = config['pilot_months']
    if not months or len(set(months)) != len(months) or len(months) > min(config['max_months'], 3):
        raise ValueError('Pilot requires one to three distinct explicit months')
    today = datetime.now(timezone.utc).strftime('%Y-%m')
    for month in months:
        if not isinstance(month, str) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])', month) or month >= today:
            raise ValueError(f'Not a completed historical month: {month}')
    if config['timezone'] != 'Pacific/Auckland' or set(config['sources']) != set(PATTERNS):
        raise ValueError('Expected Pacific/Auckland and the four core sources')
    for name in ['raw_directory', 'manifest', 'evidence_directory', 'staging_directory']:
        value = Path(config[name])
        if value.is_absolute() or '..' in value.parts:
            raise ValueError(f'Expected project-relative path: {name}')
    return config


def fetch(url):
    with urlopen(url, timeout=120) as response:
        return response.read(), dict(response.headers), response.url


def listing_entries(payload, page, source):
    entries, rejected = {}, []
    for row in html.fromstring(payload).xpath('//tr'):
        for link in row.xpath('.//a[@href]'):
            href = link.get('href')
            name = unquote(href.rsplit('/', 1)[-1])
            if not re.search(r'\.csv(?:\.gz)?$', name, re.I):
                continue
            entry = dict(filename=name, source_url=urljoin(page, href), listing_text=' '.join(row.text_content().split()))
            if 'incomplete' in (name + ' ' + entry['listing_text']).lower() or re.search(r'_I(?:\.|_)', name):
                rejected.append(dict(entry, reason='explicitly_incomplete'))
                continue
            match = re.fullmatch(PATTERNS[source], name)
            if not match:
                rejected.append(dict(entry, reason='unrecognised_filename'))
                continue
            entry['period'] = match[1] if source != 'nsp' else None
            entry['prepared_at_unzoned'] = datetime.strptime(match[2] + match[3], '%Y%m%d%H%M%S').isoformat() if source == 'reconciliation' else None
            entries[name] = entry
    return list(entries.values()), rejected


def discover(config, fetcher=fetch):
    result = {'retrieved_at_utc': utc_now(), 'pages': [], 'selected': {}}
    for source, template in config['sources'].items():
        pages = sorted({template.format(year=m[:4]) for m in config['pilot_months']})
        entries = []
        for page in pages:
            payload, headers, resolved = fetcher(page)
            found, rejected = listing_entries(payload, page, source)
            if not found:
                raise ValueError(f'No recognised source files: {page}')
            entries.extend(found)
            result['pages'].append(dict(source=source, url=page, resolved_url=resolved,
                sha256=digest(payload), recognised_files=len(found), rejected=rejected))
        periods = [None] if source == 'nsp' else config['pilot_months']
        for month in periods:
            choices = [x for x in entries if x['filename'] == config['nsp_snapshot']] if month is None else [x for x in entries if x['period'] == month.replace('-', '')]
            if not choices:
                raise ValueError(f'Missing eligible file: {source}/{month or config["nsp_snapshot"]}')
            # Reconciliation preparation timestamp is encoded in the filename;
            # choose one version, never append publications into the same fact.
            selected = max(choices, key=lambda x: (x['prepared_at_unzoned'] or '', x['filename']))
            result['selected'][f'{source}/{month or "snapshot"}'] = dict(selected, source=source, month=month,
                available_versions=[x['filename'] for x in sorted(choices, key=lambda x: x['filename'])])
    return result


def store_payload(root, config, choice, payload, headers, resolved, manifest):
    """Keep old bytes/metadata. Same content has one version, even after refresh."""
    if not payload or b'<html' in payload[:500].lower():
        raise ValueError('Empty response or HTML instead of source data')
    if choice['source'] == 'reconciliation' and not payload.startswith(b'\x1f\x8b'):
        raise ValueError('Expected gzip reconciliation payload')
    checksum = digest(payload)
    target = root / config['raw_directory'] / choice['source'] / checksum / choice['filename']
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if digest(target.read_bytes()) != checksum:
            raise ValueError(f'Immutable raw file corrupted: {target}')
    else:
        # Publish only complete bytes. A failed write leaves no raw version.
        import uuid
        temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.tmp')
        with temporary.open('xb') as stream:
            stream.write(payload)
        # Single-writer CLI; do not run concurrent refreshes against one manifest.
        if target.exists():
            if digest(target.read_bytes()) != checksum:
                raise ValueError('Concurrent raw file has unexpected bytes')
            temporary.unlink()
        else:
            temporary.rename(target)
    version_id = f'{choice["source"]}:{choice["filename"]}:{checksum}'
    if version_id not in manifest['versions']:
        lowered = {k.lower(): v for k, v in headers.items()}
        manifest['versions'][version_id] = dict(choice, sha256=checksum, bytes=len(payload),
            local_path=target.relative_to(root).as_posix(), resolved_url=resolved,
            downloaded_at_utc=utc_now(), http_last_modified=lowered.get('last-modified'), etag=lowered.get('etag'),
            snapshot_date=choice['filename'][:8] if choice['source'] == 'nsp' else None,
            publication_time_note='Listing/HTTP modification and unzoned preparation are distinct; exact publication time is not asserted.',
            revision_status='revision_eligible_not_final' if choice['source'] == 'reconciliation' else 'observed_snapshot',
            status='downloaded_sha256_verified')
    return version_id


def verify_version(root, version):
    path = root / version['local_path']
    if not path.is_file() or digest(path.read_bytes()) != version['sha256']:
        raise ValueError(f'Missing or changed pinned raw file: {version["local_path"]}')
    return path


def restore_pinned(root, config, fetcher=fetch):
    """Restore missing selected bytes only; a publisher revision is an error."""
    manifest = json.loads((root / config['manifest']).read_text())
    for version_id in manifest['selected'].values():
        version = manifest['versions'][version_id]
        target = root / version['local_path']
        if target.exists():
            verify_version(root, version)
            continue
        payload, headers, resolved = fetcher(version['source_url'])
        if digest(payload) != version['sha256']:
            raise ValueError(f'Publisher bytes changed; cannot restore pinned {version["filename"]}')
        stored = store_payload(root, config, version, payload, headers, resolved, manifest)
        if stored != version_id:
            raise ValueError('Restored version identity mismatch')
    return acquire(root, config)


def acquire(root, config, refresh=False, fetcher=fetch):
    path = root / config['manifest']
    manifest = json.loads(path.read_text()) if path.exists() else {'format_version': 1, 'versions': {}, 'selected': {}}
    if not refresh:
        expected = {f'{s}/{m}' for s in ['prices', 'generation', 'reconciliation'] for m in config['pilot_months']} | {'nsp/snapshot'}
        if set(manifest['selected']) != expected:
            raise ValueError('Pinned manifest does not match configuration; run acquire --refresh')
        for key, version_id in manifest['selected'].items():
            version = manifest['versions'][version_id]
            if key == 'nsp/snapshot' and version['filename'] != config['nsp_snapshot']:
                raise ValueError('Pinned NSP differs from configuration')
            verify_version(root, version)
        return manifest
    discovery = discover(config, fetcher)
    write_json(root / config['evidence_directory'] / 'discovery.json', discovery)
    selections = {}
    for key, choice in discovery['selected'].items():
        LOG.info('Downloading %s', choice['filename'])
        payload, headers, resolved = fetcher(choice['source_url'])
        selections[key] = store_payload(root, config, choice, payload, headers, resolved, manifest)
        # Persist new versions during recovery, but promote selections only when
        # the complete requested acquisition succeeds.
        write_json(path, manifest)
    manifest['selected'] = selections
    write_json(path, manifest)
    return manifest
