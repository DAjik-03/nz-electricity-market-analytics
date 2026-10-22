"""Exact-value validation for official daily Final Energy Prices; no imputation."""
import csv
import gzip
import hashlib
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from ingestion.intervals import day_intervals

HEADER = ['TradingDate','TradingPeriod','PointOfConnection','DollarsPerMegawattHour']


def parse_prices(payload, expected_date=None, expected_month='2025-12', require_complete=False):
    reader = csv.reader(io.StringIO(payload.decode('utf-8-sig'), newline=''))
    if next(reader, None) != HEADER:
        raise ValueError('Final Energy Prices schema drift')
    values = {}
    observed = set()
    for line, row in enumerate(reader, 2):
        if len(row) != 4: raise ValueError(f'Invalid field count at line {line}')
        day, period, poc, raw_price = row
        if date.fromisoformat(day).isoformat() != day or not day.startswith(expected_month+'-'):
            raise ValueError(f'Unexpected trading date {day}')
        if expected_date is not None and day != expected_date:
            raise ValueError(f'Row outside stated daily date: {day}')
        try:
            tp = int(period)
            price = Decimal(raw_price)
        except (ValueError, InvalidOperation) as exc:
            raise ValueError('Invalid TP or price') from exc
        if str(tp) != period or tp < 1 or tp > len(day_intervals(day)):
            raise ValueError(f'Invalid calendar trading period: {day}/{period}')
        if not poc or not price.is_finite(): raise ValueError('Empty POC or non-finite price')
        key = (day,tp,poc)
        if key in values: raise ValueError(f'Duplicate natural key: {key}')
        values[key] = price
        observed.add((day,tp))
    if not values: raise ValueError('Empty price file')
    if require_complete:
        if expected_date is None: raise ValueError('Daily coverage requires expected_date')
        expected = {(expected_date,tp) for tp in range(1,len(day_intervals(expected_date))+1)}
        if observed != expected: raise ValueError('Missing expected date/trading-period population')
    return values


def compare_populations(daily, monthly):
    dk,mk = set(daily),set(monthly)
    def describe(keys):
        return dict(key_count=len(keys),dates=sorted({k[0] for k in keys}),
                    pocs=sorted({k[2] for k in keys}),date_tp_pairs=[list(p) for p in sorted({k[:2] for k in keys})])
    overlap=dk & mk
    mismatches=[dict(trading_date=k[0],trading_period=k[1],poc=k[2],
                     daily_price=str(daily[k]),incomplete_monthly_price=str(monthly[k]))
                for k in sorted(overlap) if daily[k]!=monthly[k]]
    # Key-level differences and independently exclusive dimension populations.
    return dict(daily_union_rows=len(daily),incomplete_monthly_rows=len(monthly),overlap_keys=len(overlap),
                only_daily=describe(dk-mk),only_incomplete_monthly=describe(mk-dk),
                exclusively_daily_dates=sorted({k[0] for k in dk}-{k[0] for k in mk}),
                exclusively_monthly_dates=sorted({k[0] for k in mk}-{k[0] for k in dk}),
                exclusively_daily_pocs=sorted({k[2] for k in dk}-{k[2] for k in mk}),
                exclusively_monthly_pocs=sorted({k[2] for k in mk}-{k[2] for k in dk}),
                mismatching_overlap_values=len(mismatches),value_mismatches=mismatches)


def constituent_identity(sources):
    rows=sorted([dict(trading_date=s['trading_date'],filename=s['filename'],source_url=s['source_url'],
                      sha256=s['sha256'],price_status=s['price_status']) for s in sources],key=lambda s:s['trading_date'])
    if len({s['trading_date'] for s in rows})!=len(rows) or any(s['price_status']!='final' for s in rows):
        raise ValueError('Duplicate daily constituent or non-final source')
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def build_aggregate(values,sources):
    """Canonical CSV in deterministic gzip; member name binds constituent identity.

    A revised constituent therefore creates different artifact bytes even if its
    semantic prices are unchanged, preserving the warehouse's source+SHA identity.
    """
    identity=constituent_identity(sources)
    csv_buffer=io.StringIO(newline='')
    writer=csv.writer(csv_buffer,lineterminator='\n')
    writer.writerow(HEADER)
    for (day,tp,poc),price in sorted(values.items()): writer.writerow([day,tp,poc,format(price,'f')])
    target=io.BytesIO()
    with gzip.GzipFile(fileobj=target,mode='wb',filename=f'daily-final-{identity}.csv',mtime=0) as stream:
        stream.write(csv_buffer.getvalue().encode('utf-8'))
    return identity,target.getvalue()
