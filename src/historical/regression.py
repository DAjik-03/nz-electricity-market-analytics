"""Rollback-only original pilot selection for exact legacy regression tests.

Caller must hold the shared advisory lock and a force-rollback transaction.
Other database sessions continue seeing the committed release selection.
"""
import json
from warehouse.db import ROOT
from warehouse.loader import select_publications


def select_original_pilot_for_test(conn):
    if conn.info.transaction_status.name != 'INTRANS':
        raise ValueError('Pilot fixture requires an explicit rollback-only transaction')
    manifest=json.loads((ROOT/'outputs/pilot/source_manifest.json').read_text(encoding='utf-8'))
    ids=[]
    for vid in manifest['selected'].values():
        version=manifest['versions'][vid]
        row=conn.execute("SELECT publication_id FROM metadata.source_publication WHERE source_name=%s AND sha256=%s AND status='loaded'",
                         (version['source'],version['sha256'])).fetchone()
        if row is None: raise ValueError('Original pilot publication was not preserved')
        ids.append(row[0])
    conn.execute('DELETE FROM metadata.publication_selection')
    select_publications(conn,ids)
