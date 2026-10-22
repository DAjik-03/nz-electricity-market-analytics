"""Date-specific NZ market intervals, including repeated local wall times."""
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo
import pandas as pd

NZ = ZoneInfo('Pacific/Auckland')


@lru_cache(maxsize=4096)
def day_intervals(day):
    day = date.fromisoformat(day) if isinstance(day, str) else day
    start = datetime.combine(day, time(), NZ).astimezone(timezone.utc)
    stop = datetime.combine(day + timedelta(days=1), time(), NZ).astimezone(timezone.utc)
    rows = []
    while start < stop:
        end = start + timedelta(minutes=30)
        local, local_end = start.astimezone(NZ), end.astimezone(NZ)
        rows.append(dict(TradingDate=day.isoformat(), TradingPeriod=len(rows)+1,
            interval_start_utc=start.isoformat(), interval_end_utc=end.isoformat(),
            local_start=local.isoformat(), local_end=local_end.isoformat(),
            utc_offset_minutes=int(local.utcoffset().total_seconds()/60),
            end_utc_offset_minutes=int(local_end.utcoffset().total_seconds()/60),
            is_dst=bool(local.dst()), end_is_dst=bool(local_end.dst()),
            fold=local.fold, end_fold=local_end.fold, timezone='Pacific/Auckland'))
        start = end
    return rows


def month_calendar(month):
    day = date.fromisoformat(month + '-01')
    rows = []
    while day.strftime('%Y-%m') == month:
        rows.extend(day_intervals(day))
        day += timedelta(days=1)
    return pd.DataFrame(rows)


def boundary(day, period, end=False):
    rows = day_intervals(str(day))
    numeric = float(period)
    if not numeric.is_integer() or not 1 <= numeric <= len(rows):
        raise ValueError(f'Invalid effective boundary: {day} TP{period}')
    return rows[int(numeric)-1]['interval_end_utc' if end else 'interval_start_utc']
