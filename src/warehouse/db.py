import os
from pathlib import Path
import psycopg

ROOT = Path(__file__).resolve().parents[2]


def connect():
    settings = {}
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                settings[key.strip()] = value.strip()
    def option(name, default=None):
        return os.environ.get(name, settings.get(name, default))
    password = option('POSTGRES_PASSWORD')
    if not password or password == 'replace-with-a-local-secret':
        raise ValueError('Set POSTGRES_PASSWORD in ignored .env or the environment')
    return psycopg.connect(host=option('POSTGRES_HOST','127.0.0.1'), port=option('POSTGRES_PORT','55432'),
        user=option('POSTGRES_USER','warehouse_owner'), dbname=option('POSTGRES_DB','nz_market'),
        password=password, autocommit=True, connect_timeout=15,
        options='-c timezone=UTC -c datestyle=ISO,YMD', application_name='nz_electricity_warehouse')
