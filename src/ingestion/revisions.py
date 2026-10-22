"""Compare reconciliation publications without adding them together."""
from .parsers import KEYS, check_key


def reconciliation_delta(previous, current):
    check_key(previous, 'reconciliation')
    check_key(current, 'reconciliation')
    key = KEYS['reconciliation']
    compared = previous[key + ['KilowattHours']].merge(current[key + ['KilowattHours']], on=key,
        how='outer', suffixes=('_previous', '_current'), indicator=True, validate='one_to_one')
    matched = compared['_merge'] == 'both'
    changed = matched & (compared.KilowattHours_previous != compared.KilowattHours_current)
    return dict(previous_rows=len(previous), current_rows=len(current),
        inserted_keys=int((compared['_merge'] == 'right_only').sum()),
        removed_keys=int((compared['_merge'] == 'left_only').sum()),
        changed_measure_keys=int(changed.sum()), unchanged_keys=int((matched & ~changed).sum()),
        signed_total_kwh_change=float(current.KilowattHours.sum() - previous.KilowattHours.sum()),
        selection_policy='Current publication replaces the selected month; previous publication retained for lineage, never summed.')
