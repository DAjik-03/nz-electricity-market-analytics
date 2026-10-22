"""Effective mappings and explicit Unknown coverage, without name inference."""
import pandas as pd


def map_effective(frame, nsp, with_network):
    frame = frame.copy().reset_index(drop=True)
    frame['row_id'] = frame.index
    frame['source_position'] = frame.TradingDate.astype(str).str.replace('-', '').astype('int64') * 100 + frame.TradingPeriod
    left = ['PointOfConnection'] + (['Network'] if with_network else [])
    right = ['POC code'] + (['Network participant'] if with_network else [])
    columns = list(dict.fromkeys(right + ['NSP', 'source_start_position', 'source_end_position', 'boundary_valid',
        'Zone', 'Island', 'Network reporting region ID', 'I flow', 'X flow', 'Embedded under POC code', 'Embedded under network participant']))
    joined = frame.merge(nsp[columns], left_on=left, right_on=right, how='left', suffixes=('', '_nsp'))
    active = joined.loc[(joined.source_position >= joined.source_start_position) & (joined.source_position <= joined.source_end_position)].copy()
    if active.boundary_valid.eq(False).any():
        raise ValueError('A pilot row intersects an invalid NSP boundary; review source before mapping')
    counts = active.groupby('row_id', observed=True).size()
    frame['nsp_matches'] = frame.row_id.map(counts).fillna(0).astype('int16')
    for attribute in ['Zone', 'Island', 'Network reporting region ID']:
        source = attribute + '_nsp' if attribute in frame else attribute
        groups = active.groupby('row_id', observed=True)[source]
        acceptable = (groups.nunique(dropna=False) == 1) & (groups.count() > 0)
        mapping = groups.first().loc[acceptable].astype('string')
        frame['mapped_' + attribute] = frame.row_id.map(mapping).fillna('Unknown')
    weight = frame['source_rows'] if 'source_rows' in frame else pd.Series(1, index=frame.index)
    unknown = frame.mapped_Zone == 'Unknown'
    result = dict(aggregate_rows=len(frame), original_rows=int(weight.sum()),
        rows_without_nsp=int(weight.loc[frame.nsp_matches == 0].sum()),
        rows_with_multiple_nsp=int(weight.loc[frame.nsp_matches > 1].sum()),
        unknown_zone_rows=int(weight.loc[unknown].sum()), unknown_zone_row_pct=float(100 * weight.loc[unknown].sum() / weight.sum()),
        unknown_network_region_rows=int(weight.loc[frame['mapped_Network reporting region ID'] == 'Unknown'].sum()))
    if 'KilowattHours' in frame:
        result.update(total_kwh=float(frame.KilowattHours.sum()), unknown_zone_kwh=float(frame.loc[unknown, 'KilowattHours'].sum()))
        result['unknown_zone_energy_pct'] = 100 * result['unknown_zone_kwh'] / result['total_kwh'] if result['total_kwh'] else None
    if 'FlowDirection' in frame:
        result['by_flow'] = []
        for flow, group in frame.groupby('FlowDirection', observed=True):
            missing = group.mapped_Zone == 'Unknown'
            total = float(group.KilowattHours.sum())
            amount = float(group.loc[missing, 'KilowattHours'].sum())
            result['by_flow'].append(dict(flow=str(flow), total_kwh=total, unknown_zone_kwh=amount,
                unknown_zone_energy_pct=100*amount/total if total else None,
                original_rows=int(group.source_rows.sum()), unknown_zone_rows=int(group.loc[missing, 'source_rows'].sum())))
        disagreements = ((active.FlowDirection == 'Injection') & (active['I flow'].astype(str) != '1')) | ((active.FlowDirection == 'Offtake') & (active['X flow'].astype(str) != '1'))
        bad = active.loc[disagreements]
        result['flow_flag_disagreement_matches'] = len(bad)
        result['flow_flag_disagreement_kwh'] = float(bad.KilowattHours.sum())
        result['flow_flag_disagreement_note'] = 'Diagnostic only; I/X flags are not used to delete or reclassify measured flows. Energy may duplicate if mappings are ambiguous.'
        result['flow_flag_examples'] = bad.groupby(['PointOfConnection', 'Network', 'FlowDirection'], observed=True).KilowattHours.sum().nlargest(10).reset_index().astype(object).to_dict('records')
    problems = frame.loc[unknown | (frame.nsp_matches != 1)]
    groups = left + (['FlowDirection'] if 'FlowDirection' in frame else [])
    result['exceptions'] = problems.groupby(groups, observed=True).agg(observed_intervals=('row_id', 'size'),
        min_matches=('nsp_matches', 'min'), max_matches=('nsp_matches', 'max')).reset_index().astype(object).to_dict('records')
    return frame, result
