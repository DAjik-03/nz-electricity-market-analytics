"""A separate approved release scope leaves the frozen pilot contract unchanged."""
from pathlib import Path
import yaml
from ingestion.acquisition import PATTERNS

MONTHS=[f'2025-{m:02}' for m in range(9,13)]+[f'2026-{m:02}' for m in range(1,9)]


def load_config(path):
    config=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if config.get('release_mode')!='continuous_12_month' or config['pilot_months']!=MONTHS or config['max_months']!=12:
        raise ValueError('Only the approved 2025-09 through 2026-08 historical release is allowed')
    if config['timezone']!='Pacific/Auckland' or set(config['sources'])!=set(PATTERNS):
        raise ValueError('Unexpected timezone or source set')
    for key in ['raw_directory','manifest','evidence_directory','staging_directory']:
        value=Path(config[key])
        if value.is_absolute() or '..' in value.parts: raise ValueError('Expected project-relative path')
    return config
