"""Verified raw CSV -> COPY -> SQL facts, with per-publication transactions."""
import csv
import gzip
import hashlib
import json
import logging
import time
from datetime import datetime
from psycopg import sql
from psycopg.types.json import Jsonb
from ingestion.acquisition import acquire, load_config, verify_version, write_json
from .db import ROOT, connect

LOG = logging.getLogger(__name__)
TABLES = {'prices':'final_energy_price','reconciliation':'reconciled_volume',
          'generation':'generation_daily','nsp':'network_supply_point'}
FUNCTIONS = {'prices':'load_price','reconciliation':'load_volume','generation':'load_generation','nsp':'load_nsp'}
LOCK_ID = 7260919


def migrate(conn):
    with conn.transaction():
        conn.execute('CREATE SCHEMA IF NOT EXISTS metadata')
        conn.execute('CREATE TABLE IF NOT EXISTS metadata.schema_migration (path text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT clock_timestamp())')
    for directory in ['00_database','01_staging','02_dimensions','03_facts']:
        for path in sorted((ROOT/'sql'/directory).glob('*.sql')):
            body = path.read_text(encoding='utf-8').replace('\r\n','\n')
            checksum = hashlib.sha256(body.encode()).hexdigest()
            name = path.relative_to(ROOT).as_posix()
            previous = conn.execute('SELECT sha256 FROM metadata.schema_migration WHERE path=%s',(name,)).fetchone()
            if previous:
                if previous[0] != checksum:
                    raise ValueError(f'Applied migration changed: {name}; use a new migration or a new test database')
                continue
            with conn.transaction():
                conn.execute(body)
                conn.execute('INSERT INTO metadata.schema_migration(path,sha256) VALUES (%s,%s)',(name,checksum))
            LOG.info('Applied %s', name)


def register(conn, version):
    month = version['month'] or datetime.strptime(version['snapshot_date'], '%Y%m%d').strftime('%Y-%m')
    snapshot = datetime.strptime(version['snapshot_date'],'%Y%m%d').date() if version['snapshot_date'] else None
    conn.execute('''INSERT INTO metadata.source_publication
        (source_name,source_month,filename,sha256,prepared_at_unzoned,snapshot_date,downloaded_at,
         http_last_modified,etag,file_size_bytes,source_url,manifest_metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_name,sha256) DO NOTHING''',
        (version['source'],month+'-01',version['filename'],version['sha256'],version['prepared_at_unzoned'],snapshot,
         version['downloaded_at_utc'],version['http_last_modified'],version['etag'],version['bytes'],version['source_url'],Jsonb(version)))
    row = conn.execute('SELECT publication_id,status,source_month FROM metadata.source_publication WHERE source_name=%s AND sha256=%s',
        (version['source'],version['sha256'])).fetchone()
    if row[2].isoformat() != month+'-01':
        raise ValueError('Immutable content registered against a different month')
    return row[0], row[1]


def copy_source(conn, version, pid):
    path = verify_version(ROOT, version)
    opener = gzip.open if path.suffix == '.gz' else open
    expected = json.loads((ROOT/'config/source_schema.json').read_text())[version['source']]
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        header = next(csv.reader(stream))
    if header != expected:
        raise ValueError('Warehouse COPY requires the exact approved header order')
    conn.execute("SELECT set_config('warehouse.publication_id',%s,true)",(str(pid),))
    conn.execute("SELECT setval('staging.source_row_number',1,false)")
    query = sql.SQL('COPY staging.{} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING \'UTF8\')').format(
        sql.Identifier(TABLES[version['source']]),sql.SQL(',').join(map(sql.Identifier,header)))
    with opener(path, 'rb') as stream, conn.cursor().copy(query) as copy:
        while block := stream.read(1024*1024):
            copy.write(block)
    conn.execute(sql.SQL('ANALYZE staging.{}').format(sql.Identifier(TABLES[version['source']])))


def select_publications(conn, ids):
    """One analytical release switches all selected publications atomically."""
    with conn.transaction():
        for pid in ids:
            conn.execute('''INSERT INTO metadata.publication_selection(source_name,source_month,publication_id)
                SELECT source_name,source_month,publication_id FROM metadata.source_publication WHERE publication_id=%s
                ON CONFLICT (source_name,source_month) DO UPDATE SET publication_id=EXCLUDED.publication_id, selected_at=clock_timestamp()
                WHERE publication_selection.publication_id<>EXCLUDED.publication_id''',(pid,))


def validate_publication_totals(conn, source, pid):
    """Reject lost rows or changed native measures before committing loaded status."""
    if source == 'nsp':
        stage = conn.execute('SELECT count(*) FROM staging.network_supply_point WHERE publication_id=%s', (pid,)).fetchone()
        core = conn.execute('SELECT count(*) FROM core.dim_nsp_version WHERE publication_id=%s', (pid,)).fetchone()
    elif source == 'prices':
        stage = conn.execute('SELECT count(*),sum("DollarsPerMegawattHour"::numeric) FROM staging.final_energy_price WHERE publication_id=%s', (pid,)).fetchone()
        core = conn.execute('SELECT count(*),sum(dollars_per_mwh) FROM core.fact_price WHERE publication_id=%s', (pid,)).fetchone()
    elif source == 'reconciliation':
        stage = conn.execute('SELECT "FlowDirection",count(*),sum("KilowattHours"::numeric) FROM staging.reconciled_volume WHERE publication_id=%s GROUP BY 1 ORDER BY 1', (pid,)).fetchall()
        core = conn.execute('SELECT flow_direction,count(*),sum(kilowatt_hours) FROM core.fact_reconciled_volume WHERE publication_id=%s GROUP BY 1 ORDER BY 1', (pid,)).fetchall()
    elif source == 'generation':
        values = sql.SQL(',').join(sql.SQL('(s.{})').format(sql.Identifier(f'TP{i}')) for i in range(1,51))
        stage = conn.execute(sql.SQL('SELECT count(v.kwh),sum(v.kwh::numeric) FROM staging.generation_daily s CROSS JOIN LATERAL (VALUES {}) v(kwh) WHERE publication_id=%s').format(values), (pid,)).fetchone()
        core = conn.execute('SELECT count(*),sum(kilowatt_hours) FROM core.fact_generation_connection WHERE publication_id=%s', (pid,)).fetchone()
    else:
        raise ValueError(f'Unsupported source: {source}')
    if stage != core:
        raise ValueError(f'Publication {pid} staging/core native totals or counts differ')
    return dict(staging=stage,core=core)


def load_publication(conn, version, snapshot_pid=None, fail_after_copy=False):
    started=time.perf_counter()
    pid,status=register(conn,version)
    if status=='loaded':
        if version['source'] in ['generation','reconciliation']:
            table='fact_generation_connection' if version['source']=='generation' else 'fact_reconciled_volume'
            actual=conn.execute(sql.SQL('SELECT nsp_snapshot_publication_id FROM core.{} WHERE publication_id=%s LIMIT 1').format(sql.Identifier(table)),(pid,)).fetchone()
            if actual and actual[0]!=snapshot_pid:
                raise ValueError('Loaded publication uses another NSP snapshot; explicit remapping release required')
        LOG.info('Unchanged loaded publication %s: skipped',version['filename'])
        return dict(publication_id=pid,source=version['source'],filename=version['filename'],status='skipped',elapsed_seconds=round(time.perf_counter()-started,3))
    attempt=conn.execute("INSERT INTO metadata.load_attempt(publication_id,status) VALUES (%s,'running') RETURNING attempt_id",(pid,)).fetchone()[0]
    try:
        with conn.transaction():
            conn.execute("SET LOCAL work_mem='128MB'")
            conn.execute("SET LOCAL jit=off")
            LOG.info('COPY %s',version['filename'])
            copy_source(conn,version,pid)
            if fail_after_copy:
                raise RuntimeError('Injected failure after COPY')
            if version['source']!='nsp':
                conn.execute('SELECT core.ensure_calendar(%s::date)',(version['month']+'-01',))
            for table in ['dim_date','dim_trading_interval','dim_connection','dim_nsp_version','dim_generator','dim_participant']:
                conn.execute(sql.SQL('ANALYZE core.{}').format(sql.Identifier(table)))
            LOG.info('SQL transform %s',version['filename'])
            fn=FUNCTIONS[version['source']]
            args=(pid,snapshot_pid) if version['source'] in ['generation','reconciliation'] else (pid,)
            total=conn.execute(sql.SQL('SELECT core.{}({})').format(sql.Identifier(fn),sql.SQL(',').join(sql.Placeholder() for _ in args)),args).fetchone()[0]
            staged=conn.execute(sql.SQL('SELECT count(*) FROM staging.{} WHERE publication_id=%s').format(sql.Identifier(TABLES[version['source']])),(pid,)).fetchone()[0]
            validate_publication_totals(conn,version['source'],pid)
            conn.execute("UPDATE metadata.source_publication SET status='loaded',staged_rows=%s,fact_rows=%s,loaded_at=clock_timestamp() WHERE publication_id=%s",(staged,total,pid))
            elapsed=round(time.perf_counter()-started,3)
            conn.execute("UPDATE metadata.load_attempt SET status='succeeded',finished_at=clock_timestamp(),elapsed_seconds=%s WHERE attempt_id=%s",(elapsed,attempt))
    except Exception as error:
        # The COPY, dimensions, facts and successful status were rolled back.
        conn.execute("UPDATE metadata.source_publication SET status='failed' WHERE publication_id=%s AND status<>'loaded'",(pid,))
        conn.execute("UPDATE metadata.load_attempt SET status='failed',finished_at=clock_timestamp(),error_message=%s WHERE attempt_id=%s",(str(error)[:2000],attempt))
        raise
    LOG.info('Loaded %s: staging=%s core=%s seconds=%.3f',version['filename'],staged,total,elapsed)
    return dict(publication_id=pid,source=version['source'],filename=version['filename'],status='loaded',staging_rows=staged,core_rows=total,elapsed_seconds=elapsed)


def run(command):
    config=load_config(ROOT/'config/project_config.yml')
    # Offline verification only. No source downloads or refresh are performed.
    manifest=acquire(ROOT,config)
    output=ROOT/'outputs/warehouse'
    output.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.StreamHandler(),logging.FileHandler(output/'warehouse.log',encoding='utf-8')])
    with connect() as conn:
        conn.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        try:
            migrate(conn)
            if command=='init': return
            versions=[manifest['versions'][vid] for key,vid in sorted(manifest['selected'].items(),key=lambda x:(not x[0].startswith('nsp/'),x[0]))]
            report=[]
            snapshot_pid=None
            for version in versions:
                item=load_publication(conn,version,snapshot_pid)
                report.append(item)
                if version['source']=='nsp': snapshot_pid=item['publication_id']
                write_json(output/'latest_load.json',dict(status='running',publications=report))
            select_publications(conn,[item['publication_id'] for item in report])
            write_json(output/'latest_load.json',dict(status='succeeded',publications=report))
        except Exception as error:
            write_json(output/'latest_load.json',dict(status='failed',error_type=type(error).__name__,error=str(error),
                publications=locals().get('report',[])))
            LOG.exception('Warehouse load failed; prior committed publications are preserved')
            raise
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))
