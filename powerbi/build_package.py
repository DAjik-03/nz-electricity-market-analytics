"""Rebuild text-only Power BI inputs. No database writes or credentials.

Run from any directory with Python 3.12. Outputs are reviewable source files,
not a PBIX/PBIP. Validation is separate in validate_package.py.
"""
from pathlib import Path
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FINGERPRINT = 'b87ef82066c5bcd7055d350da94b28811467c3e0c2687489fb8363c5cd6e2cf6'

def write(path, text):
    path = HERE / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(line.rstrip() for line in text.splitlines()).rstrip() + '\n', encoding='utf-8')

def js(path, obj):
    write(path, json.dumps(obj, indent=2, ensure_ascii=False))

def read_analysis(name):
    return json.loads((ROOT/'outputs/analysis'/name).read_text(encoding='utf-8'))

queries = {}
def sql(name, text):
    queries[name] = text.strip().rstrip(';')
    write('sql/'+name+'.sql', queries[name]+';')

components = '''interval_id,offtake_kwh,priced_offtake_kwh,price_numerator,
 weighted_price,demand_mw,generation_kwh,renewable_kwh,fossil_kwh,storage_kwh,
 unclassified_kwh,known_zone_offtake_kwh,known_zone_generation_kwh,is_price_pressure'''
sql('FactNational', f'SELECT {components},regional_price_spread,represented_zones,expected_zones\nFROM analytics.mart_market_interval_national')
sql('FactZone', f'SELECT zone,{components}\nFROM analytics.mart_market_interval_zone')
sql('DimInterval', '''SELECT interval_id,trading_date,trading_period,
 start_utc AT TIME ZONE 'UTC' AS start_utc,end_utc AT TIME ZONE 'UTC' AS end_utc,
 local_start,local_end,expected_periods,extract(hour FROM local_start)::int AS local_hour,
 extract(epoch FROM (local_start-(start_utc AT TIME ZONE 'UTC')))::int/60 AS utc_offset_minutes,
 (extract(epoch FROM (local_start-(start_utc AT TIME ZONE 'UTC')))::int=46800) AS is_dst,
 (row_number() OVER(PARTITION BY local_start ORDER BY start_utc)-1)::int AS fold
FROM analytics.mart_market_interval_national''')
sql('DimZone', "SELECT DISTINCT zone FROM analytics.mart_market_interval_zone")
sql('Threshold', '''SELECT scope,zone,p99_price,population_intervals,
 first_start_utc AT TIME ZONE 'UTC' AS first_start_utc,
 last_end_utc AT TIME ZONE 'UTC' AS last_end_utc,percentile,comparison
FROM analytics.mart_price_pressure_threshold''')
sql('Events', '''SELECT event_id,scope,zone,start_utc AT TIME ZONE 'UTC' AS start_utc,
 end_utc AT TIME ZONE 'UTC' AS end_utc,local_start,local_end,local_start::date AS start_date,
 interval_count,duration_hours,weighted_price,peak_weighted_price,p99_threshold,
 average_demand_mw,peak_demand_mw,total_offtake_kwh,priced_offtake_kwh,price_numerator,
 average_regional_spread,peak_regional_spread,listed_generation_kwh,
 renewable_kwh,fossil_kwh,storage_kwh,unclassified_kwh,renewable_primary_share_pct,
 classification_coverage_pct,price_weighting_coverage_pct,offtake_zone_coverage_pct,
 generation_zone_coverage_pct,refresh_id,input_fingerprint,dq_run_id,dq_as_of_date,dq_status
FROM analytics.mart_price_event_context''')
sql('EventInterval', '''SELECT e.event_id,i.interval_id
FROM analytics.mart_price_pressure_event e
JOIN analytics.mart_market_interval_national i
 ON i.start_utc>=e.start_utc AND i.start_utc<e.end_utc''')
sql('RegionalSignal', '''WITH flags AS (
 SELECT interval_id,min(start_utc) AS start_utc,max(end_utc) AS end_utc,
 count(*) FILTER(WHERE is_price_pressure)::int AS zones_flagged
 FROM analytics.mart_market_interval_zone
 WHERE zone IN ('CNI','LNI','LSI','UNI','USI') GROUP BY interval_id
), marked AS (
 SELECT *,CASE WHEN lag(end_utc) OVER(ORDER BY start_utc)=start_utc THEN 0 ELSE 1 END AS begins
 FROM flags WHERE zones_flagged>0
), episodes AS (
 SELECT interval_id,sum(begins) OVER(ORDER BY start_utc)::bigint AS episode_id FROM marked
)
SELECT f.interval_id,f.zones_flagged,e.episode_id,
 f.zones_flagged>0 AND NOT n.is_price_pressure AS zone_only
FROM flags f LEFT JOIN episodes e USING(interval_id)
JOIN analytics.mart_market_interval_national n USING(interval_id)''')
sql('SourceQuality', '''SELECT run_id,source_name,source_month,denominator_unit,total_value,
 known_value,unknown_value,coverage_pct,as_of_date,refresh_id
FROM analytics.mart_source_quality''')
sql('DQResults', '''SELECT run_id,rule_id,rule_snapshot::text AS rule_snapshot,result_status,
 affected_rows,observed_value::text AS observed_value,expected_value,
 coverage_pct,details::text AS details,as_of_date,refresh_id
FROM analytics.mart_quality_results''')
sql('Release', '''SELECT refresh_id,input_fingerprint,dq_run_id,dq_as_of_date,dq_status,
 is_current,status,completed_at AT TIME ZONE 'UTC' AS completed_at_utc,
 input_manifest::text AS input_manifest
FROM analytics.refresh_status''')
sql('Classification', '''SELECT classification_version,fuel_code,tech_code,standard_category,
 generation_role,energy_status,evidence_url,review_status,rationale
FROM analytics.ref_generation_classification WHERE classification_version=1''')
src = (ROOT/'sql/05_analysis/04_demand_association.sql').read_text(encoding='utf-8')
sql('DemandBenchmark', src.split('-- name: demand_hour_adjusted\n')[1])

# One native source connection. Password is supplied through Desktop, never M.
write('queries/pServer.pq', '"127.0.0.1:55432" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]')
write('queries/pDatabase.pq', '"nz_market" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]')
write('queries/Source.pq', 'PostgreSQL.Database(pServer, pDatabase, [CreateNavigationProperties=false, CommandTimeout=#duration(0,0,10,0)])')
write('queries/ReleaseGate.pq', f'''let
    T = Value.NativeQuery(Source, "SELECT refresh_id,input_fingerprint,dq_run_id,is_current,status FROM analytics.refresh_status", null, [EnableFolding=false]),
    R = if Table.RowCount(T)=1 then T{{0}} else error "Expected exactly one approved release",
    Valid = R[refresh_id]=38 and R[dq_run_id]=5 and R[is_current]=true and R[status]="COMPLETED" and R[input_fingerprint]="{FINGERPRINT}"
in if Valid then true else error "Release differs from approved Phase 5. Investigate; do not refresh/promote warehouse."''')
for name, statement in queries.items():
    quoted = statement.replace('"','""').replace('\n','#(lf)')
    # Type is supplied by PostgreSQL connector; date dimension constructed with explicit types below.
    write('queries/'+name+'.pq', f'''let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "{quoted}", null, [EnableFolding=false]) else error "Release gate failed"
in Rows''')
write('queries/DimDate.pq', '''let
    Dates = List.Dates(#date(2025,9,1),365,#duration(1,0,0,0)),
    Base = Table.FromColumns({Dates},type table [Date=date]),
    Y = Table.AddColumn(Base,"Year",each Date.Year([Date]),Int64.Type),
    MN = Table.AddColumn(Y,"Month Number",each Date.Month([Date]),Int64.Type),
    M = Table.AddColumn(MN,"Month",each Date.ToText([Date],"MMM","en-NZ"),type text),
    YM = Table.AddColumn(M,"Year-Month",each Date.ToText([Date],"yyyy-MM","en-NZ"),type text),
    YMK = Table.AddColumn(YM,"Year-Month Sort",each [Year]*100+[Month Number],Int64.Type),
    Q = Table.AddColumn(YMK,"Quarter",each "Q" & Text.From(Date.QuarterOfYear([Date])),type text),
    WN = Table.AddColumn(Q,"Weekday Number",each Date.DayOfWeek([Date],Day.Monday)+1,Int64.Type),
    W = Table.AddColumn(WN,"Weekday",each Date.ToText([Date],"ddd","en-NZ"),type text),
    DT = Table.AddColumn(W,"Day Type",each if [Weekday Number]>5 then "Weekend" else "Weekday",type text)
in DT''')
write('queries/DimMonth.pq','Table.Distinct(Table.SelectColumns(DimDate,{"Year-Month","Year-Month Sort"}))')
# Month dimension intentionally has matching date key for source-quality monthly grain.
write('queries/DimMonth.pq', '''let
    M = Table.Distinct(Table.SelectColumns(DimDate,{"Year-Month","Year-Month Sort"})),
    D = Table.AddColumn(M,"MonthStart",each Date.FromText([#"Year-Month"] & "-01"),type date)
in D''')

cases = read_analysis('representative_events.json')
external = read_analysis('external_context.json')
case_rows=[]
for case in cases:
    ext = next(e for e in external['sources'] if case['case_id'] in e['cases'])
    case_rows.append({k:case[k] for k in ('case_id','event_id','selection_reason')} | {k:ext[k] for k in ('publisher','title','url','locator','supported_context','qualification')} | {'review_date': external['review_date_local']})
js('case_presets.json', case_rows)
def mtext(s): return '"'+str(s).replace('"','""').replace('\n','#(lf)')+'"'
write('queries/CaseContext.pq', '#table(type table ['+', '.join(k+'=text' for k in case_rows[0])+'], {\n'+',\n'.join('  {'+', '.join(mtext(v) for v in r.values())+'}' for r in case_rows)+'\n})')

rels = [
 ('DimDate','Date','DimInterval','trading_date'),
 ('DimInterval','interval_id','FactNational','interval_id'),
 ('DimInterval','interval_id','FactZone','interval_id'),
 ('DimZone','zone','FactZone','zone'),
 ('DimInterval','interval_id','RegionalSignal','interval_id'),
 ('Events','event_id','EventInterval','event_id'),
 ('Events','event_id','CaseContext','event_id'),
 ('DimMonth','MonthStart','SourceQuality','source_month')]
js('relationships.json',[dict(one_table=a,one_column=b,many_table=c,many_column=d,cardinality='one-to-many',direction='single',active=True) for a,b,c,d in rels])
write('model_relationships.mmd','flowchart LR\n'+'\n'.join(f'    {a} -->|"{b} → {d}; 1:*"| {c}' for a,b,c,d in rels)+'''
    Threshold["Threshold · disconnected / full release"]
    DemandBenchmark["DemandBenchmark · disconnected / full release"]
    DQResults["DQResults · release 38 / run 5"]
    Release["Release · disconnected"]
    Classification["Classification · reference only"]
    EventInterval -. "measure-only TREATAS · no relationship" .-> DimInterval''')

measures=[]
def measure(name, expression, folder, fmt='#,0.00', description=''):
    measures.append(dict(name=name,expression=expression,display_folder=folder,format_string=fmt,description=description,home_table='FactNational'))
def s(t,c): return f'SUM({t}[{c}])'
for prefix,table in [('', 'FactNational'),('Zone ', 'FactZone')]:
    folder = 'National' if not prefix else 'Zone'
    guard = 'IF(HASONEVALUE(DimZone[zone]), {expr})' if prefix else '{expr}'
    def add(n,e,f='#,0.00',d=''):
        measure(prefix+n,guard.format(expr=e),folder,f,d)
    add('Weighted Wholesale Price',f'DIVIDE({s(table,"price_numerator")}, {s(table,"priced_offtake_kwh")})',d='NZD/MWh; ratio of sums, never average weighted prices.')
    valid=f'FILTER({table}, NOT ISBLANK({table}[weighted_price]))'
    add('P95 Price',f'IF(COUNTROWS({valid})>0, PERCENTILEX.INC({valid}, {table}[weighted_price], 0.95))')
    add('Price Volatility',f'VAR N=COUNTROWS({valid}) RETURN IF(N=1,0,IF(N>1,STDEVX.P({valid},{table}[weighted_price])))',d='Population SD of half-hour weighted prices; blanks excluded; one observation = 0.')
    for n,col,div in [('Total Demand GWh','offtake_kwh',1000000),('Listed Generation GWh','generation_kwh',1000000),('Renewable GWh','renewable_kwh',1000000),('Fossil Thermal GWh','fossil_kwh',1000000),('Storage GWh','storage_kwh',1000000),('Unclassified GWh','unclassified_kwh',1000000)]:
        add(n,f'DIVIDE({s(table,col)},{div})')
    add('Peak Demand MW',f'MAX({table}[demand_mw])')
    add('Mean Demand MW',f'AVERAGE({table}[demand_mw])')
    for n,num,den in [('Renewable Primary Share',s(table,'renewable_kwh'),f'{s(table,"renewable_kwh")}+{s(table,"fossil_kwh")}'),('Fossil Thermal Share',s(table,'fossil_kwh'),f'{s(table,"renewable_kwh")}+{s(table,"fossil_kwh")}'),('Classification Coverage',f'{s(table,"generation_kwh")}-{s(table,"unclassified_kwh")}',s(table,'generation_kwh')),('Offtake Zone Coverage',s(table,'known_zone_offtake_kwh'),s(table,'offtake_kwh')),('Generation Zone Coverage',s(table,'known_zone_generation_kwh'),s(table,'generation_kwh')),('Priced Offtake Coverage',s(table,'priced_offtake_kwh'),s(table,'offtake_kwh'))]:
        add(n,f'DIVIDE({num},{den})','0.00%')
    flagged=f'IF(COUNTROWS({table})>0,COALESCE(COUNTROWS(FILTER({table},{table}[is_price_pressure]=TRUE())),0))'
    if prefix:
        flagged=f'IF(NOT ISBLANK([Zone Full-period P99 threshold]),{flagged})'
    add('Flagged Half-hours',flagged,'#,0')
    add('Pressure Hours',f'0.5*[{prefix}Flagged Half-hours]')

measure('Full-period P99 threshold','CALCULATE(MAX(Threshold[p99_price]),REMOVEFILTERS(Threshold),Threshold[scope]="National")','Threshold',description='Full release; disconnected from Date. Not an official scarcity threshold.')
measure('Zone Full-period P99 threshold','VAR Z=SELECTEDVALUE(DimZone[zone]) RETURN IF(HASONEVALUE(DimZone[zone]),CALCULATE(MAX(Threshold[p99_price]),REMOVEFILTERS(Threshold),Threshold[scope]="Zone",Threshold[zone]=Z))','Threshold')
measure('Regional Spread','AVERAGE(FactNational[regional_price_spread])','Regional',description='Mean of complete five-known-Zone half-hour ranges; date filter only.')
measure('Spread Eligible Half-hours','COUNT(FactNational[regional_price_spread])','Regional','#,0')
measure('Any-Zone Flagged Half-hours','COUNTROWS(FILTER(RegionalSignal,RegionalSignal[zones_flagged]>0))','Regional','#,0')
measure('Simultaneous Zones','MAX(RegionalSignal[zones_flagged])','Regional','0',description='Use at interval grain; at higher grain means maximum simultaneous count.')
measure('Zone-only Half-hours','COUNTROWS(FILTER(RegionalSignal,RegionalSignal[zone_only]=TRUE()))','Regional','#,0')
measure('Cross-regional Episodes','COUNTROWS(FILTER(VALUES(RegionalSignal[episode_id]),NOT ISBLANK(RegionalSignal[episode_id])))','Regional','#,0',description='Episodes intersecting selection; assigned on full release; non-additive across dates.')
# Start-date event counts: Events remains disconnected from the reporting calendar.
measure('Pressure Events','COALESCE(CALCULATE(COUNTROWS(Events),REMOVEFILTERS(Events),Events[scope]="National",TREATAS(VALUES(DimDate[Date]),Events[start_date])),0)','Events','#,0','National events starting on selected dates; not all scoped records.')
measure('Zone Pressure Events','VAR Z=SELECTEDVALUE(DimZone[zone]) RETURN IF(HASONEVALUE(DimZone[zone]) && NOT ISBLANK([Zone Full-period P99 threshold]),COALESCE(CALCULATE(COUNTROWS(Events),REMOVEFILTERS(Events),Events[scope]="Zone",Events[zone]=Z,TREATAS(VALUES(DimDate[Date]),Events[start_date])),0))','Events','#,0')
for name,col,fmt in [('Event Duration','duration_hours','0.0'),('Peak Event Price','peak_weighted_price','#,0.00'),('Event Weighted Price','weighted_price','#,0.00'),('Event Mean Demand MW','average_demand_mw','#,0.00'),('Event Regional Spread','average_regional_spread','#,0.00')]:
    measure(name,f'IF(HASONEVALUE(Events[event_id]),SELECTEDVALUE(Events[{col}]))','Event detail',fmt,'Full selected scoped event, ignoring global Date.')
measure('Event Selection Status','IF(HASONEVALUE(Events[event_id]),SELECTEDVALUE(Events[scope]) & " / " & SELECTEDVALUE(Events[zone]),"Select one event")','Event detail','')
# Full event membership applies after removing calendar filter, including for local-date crossing.
for name,base in [('Event National Demand MW','Mean Demand MW'),('Event National Weighted Price','Weighted Wholesale Price'),('Event National Renewable Share','Renewable Primary Share'),('Event National Classification Coverage','Classification Coverage'),('Event National Offtake Coverage','Offtake Zone Coverage'),('Event National Generation Coverage','Generation Zone Coverage')]:
    measure(name,f'VAR IDs=CALCULATETABLE(VALUES(EventInterval[interval_id])) RETURN IF(HASONEVALUE(Events[event_id]),CALCULATE([{base}],REMOVEFILTERS(DimDate),REMOVEFILTERS(DimInterval),TREATAS(IDs,DimInterval[interval_id])))','Event context','0.00%' if 'Share' in name or 'Coverage' in name else '#,0.00','National context, even for a regional event.')
measure('Event Interval Visible','VAR I=SELECTEDVALUE(DimInterval[interval_id]) VAR IDs=VALUES(EventInterval[interval_id]) RETURN IF(HASONEVALUE(Events[event_id]) && I IN IDs,1,0)','Event detail','0','Apply visual filter =1 on interval heatmap; no global date on event page.')
measure('Zone Pressure Flag','IF(HASONEVALUE(DimZone[zone]) && HASONEVALUE(DimInterval[interval_id]) && NOT ISBLANK([Zone Full-period P99 threshold]),IF(COUNTROWS(FILTER(FactZone,FactZone[is_price_pressure]=TRUE()))>0,1,0))','Event detail','0')
measure('Source Geography Coverage','IF(HASONEVALUE(SourceQuality[source_name]),DIVIDE(SUM(SourceQuality[known_value]),SUM(SourceQuality[total_value])))','Quality','0.0000%','Never pool sources with different denominators.')
measure('Unknown Source Quantity','IF(HASONEVALUE(SourceQuality[source_name]),SUM(SourceQuality[unknown_value]))','Quality','#,0.00','Unit comes from denominator_unit; rows and kWh never added.')
for status in ('PASS','WARN','FAIL'):
    measure('DQ '+status,f'COALESCE(CALCULATE(COUNTROWS(DQResults),REMOVEFILTERS(DQResults),DQResults[result_status]="{status}"),0)','Quality','0','Full retained run; no composite score.')
for name,col in [('Release Pressure Mean MW','pressure_mean_mw'),('Release Matched Comparator MW','matched_control_mean_mw'),('Release Matched Difference MW','mean_difference_mw')]:
    measure(name,f'MAX(DemandBenchmark[{col}])','Fixed release comparison','#,0.00','Full-release month/hour standardisation, not affected by dates; descriptive, not causal.')
measure('Release Matched Difference Pct','DIVIDE(MAX(DemandBenchmark[difference_pct]),100)','Fixed release comparison','0.00%')
measure('Selected Pressure Mean MW','CALCULATE([Mean Demand MW],FactNational[is_price_pressure]=TRUE())','Pressure context')
measure('Selected Non-pressure Mean MW','CALCULATE([Mean Demand MW],FactNational[is_price_pressure]=FALSE())','Pressure context')
measure('Unknown Offtake GWh','DIVIDE(SUM(FactNational[offtake_kwh])-SUM(FactNational[known_zone_offtake_kwh]),1000000)','Quality')
measure('Unknown Generation GWh','DIVIDE(SUM(FactNational[generation_kwh])-SUM(FactNational[known_zone_generation_kwh]),1000000)','Quality')
measure('Event Interval Price','VAR S=SELECTEDVALUE(Events[scope]) VAR Z=SELECTEDVALUE(Events[zone]) RETURN IF(HASONEVALUE(Events[event_id]) && [Event Interval Visible]=1,IF(S="National",[Weighted Wholesale Price],CALCULATE([Zone Weighted Wholesale Price],REMOVEFILTERS(DimZone),TREATAS({Z},DimZone[zone]))))','Event detail',description='Scoped event interval price; use UTC interval axis and Event Interval Visible=1.')
# Keep only exposed visuals/tooltips and their transitive dependencies.
# Page specifications are tracked; rebuild them first after a visual change.
page_spec=json.loads((HERE/'page_specification.json').read_text(encoding='utf-8'))
used={name for p in page_spec for v in p['visuals'] for name in v['values']}
used.update({'Spread Eligible Half-hours','Event Selection Status','Zone Priced Offtake Coverage'})
by_name={m['name']:m for m in measures}
pending=list(used)
while pending:
    name=pending.pop()
    expression=re.sub(r'\b\w+\[[^\]]+\]','',by_name[name]['expression'])
    for dep in re.findall(r'\[([^\]]+)\]',expression):
        if dep not in used:
            used.add(dep);pending.append(dep)
removed=[m['name'] for m in measures if m['name'] not in used]
measures=[m for m in measures if m['name'] in used]
for m in measures:
    old=m['display_folder']; name=m['name']
    if old in ('Event detail','Event context'): folder='Event Investigation'
    elif old=='Quality' or 'Coverage' in name: folder='Coverage and Data Quality'
    elif old in ('Threshold','Events') or 'Flagged' in name or 'Pressure Hours' in name: folder='Price Pressure'
    elif old=='Regional': folder='Regional'
    elif 'Demand' in name or old=='Fixed release comparison': folder='Demand'
    elif 'Price' in name or 'Volatility' in name: folder='Price'
    else: folder='Generation'
    if old in ('National','Zone'): folder+='\\'+old
    m['display_folder']=folder
js('measure_review.json',dict(retained=len(measures),removed_unused=removed,additional_exposures={
 'Spread Eligible Half-hours':'Spread tooltip', 'Event Selection Status':'Page 4 dynamic title',
 'Zone Priced Offtake Coverage':'Regional price tooltip'},engine_validated=False))
js('measure_catalog.json',measures)
write('measures.dax','// Create each measure individually using New measure. Not a standalone DAX query.\n'+ '\n\n'.join(f'// Folder: {m["display_folder"]}; Format: {m["format_string"]}\n// {m["description"]}\n{m["name"]} =\n{m["expression"]}' for m in measures))
js('theme.json',dict(name='NZ Electricity | restrained',dataColors=['#12647A','#B34F19','#527A43','#755691','#687580'],background='#F3F6F8',foreground='#172B3A',tableAccent='#12647A'))
js('package_manifest.json',dict(artifact='Power BI build package; not a compiled report',approved_commit='84fa1474ad1e55944df87792357beb34dcec4edf',refresh_id=38,dq_run_id=5,input_fingerprint=FINGERPRINT,sql_queries=list(queries),measure_count=len(measures),mode='Import',date_start='2025-09-01',date_end='2026-08-31'))
print(f'Generated {len(queries)} SQL/Power Query imports and {len(measures)} DAX measures.')
