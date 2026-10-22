"""Run the explicitly bounded Phase 1A pilot; never creates warehouse objects."""
import argparse
import logging
from pathlib import Path
from ingestion.acquisition import acquire, load_config, restore_pinned, utc_now, write_json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['acquire', 'restore', 'validate'])
    parser.add_argument('--config', type=Path, default=ROOT / 'config/project_config.yml')
    parser.add_argument('--refresh', action='store_true', help='Re-discover and fetch source bytes to detect publisher revisions')
    args = parser.parse_args()
    config = load_config(args.config)
    evidence = ROOT / config['evidence_directory']
    evidence.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.StreamHandler(), logging.FileHandler(evidence / 'pilot.log', encoding='utf-8')])
    state = dict(command=args.command, started_at_utc=utc_now(), status='running')
    write_json(evidence / 'run_state.json', state)
    try:
        if args.command == 'restore' and args.refresh:
            raise ValueError('Restore is pinned; --refresh is a separate acquisition action')
        manifest = restore_pinned(ROOT, config) if args.command == 'restore' else acquire(ROOT, config, args.refresh)
        if args.command == 'validate':
            from ingestion.validation import validate_pilot
            validate_pilot(ROOT, config, manifest)
        state.update(status='succeeded', finished_at_utc=utc_now())
    except Exception as error:
        state.update(status='failed', finished_at_utc=utc_now(), error_type=type(error).__name__, error=str(error))
        logging.exception('Pilot failed; preserve files and inspect run_state.json')
        raise
    finally:
        write_json(evidence / 'run_state.json', state)


if __name__ == '__main__':
    main()
