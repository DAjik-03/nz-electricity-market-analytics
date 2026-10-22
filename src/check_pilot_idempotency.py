"""Verify an unchanged offline re-run preserves evidence and staging bytes/mtimes."""
import json
from pathlib import Path
from ingestion.acquisition import acquire, digest, load_config, write_json
from ingestion.validation import validate_pilot

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = load_config(ROOT / 'config/project_config.yml')
    result_path = ROOT / config['evidence_directory'] / 'validation.json'
    result = json.loads(result_path.read_text(encoding='utf-8'))
    paths = [ROOT / config['manifest'], result_path] + [ROOT / item['path'] for item in result['artefacts']]
    before = {p.as_posix():(digest(p.read_bytes()), p.stat().st_mtime_ns) for p in paths}
    manifest = acquire(ROOT, config, refresh=False)
    validate_pilot(ROOT, config, manifest)
    after = {p.as_posix():(digest(p.read_bytes()), p.stat().st_mtime_ns) for p in paths}
    if before != after:
        raise AssertionError('Unchanged re-run altered an evidence or staging artefact')
    write_json(ROOT / config['evidence_directory'] / 'idempotency.json', dict(
        mode='offline pinned raw and derived hash verification; no network',
        selected_versions=manifest['selected'], code_sha256=result['code_sha256'],
        files_checked=len(paths), bytes_unchanged=True, modification_times_unchanged=True,
        note='Online changed-byte behaviour is covered by version-store and failure unit tests; Phase 0/current same-byte comparison supplies real-source evidence.'))
    print(f'PASS: {len(paths)} files retained identical bytes and modification times')


if __name__ == '__main__':
    main()
