"""Deterministic native Power BI sources from the approved Phase 6 inputs.

Generation is not Desktop acceptance. No database connection is made here.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'powerbi'
MODEL = P / 'NZ_Electricity_Market.SemanticModel'
REPORT = P / 'NZ_Electricity_Market.Report'
BASE = 'https://developer.microsoft.com/json-schemas/fabric/'
VERSIONS = {'visualContainer':'2.12.0','page':'2.1.0','report':'3.3.0',
            'bookmark':'2.1.0','bookmarksMetadata':'1.0.0','pagesMetadata':'1.1.0','versionMetadata':'1.0.0'}

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding='utf-8') != text:
        path.write_text(text, encoding='utf-8', newline='\n')
def out(path, value): write(path, json.dumps(value, ensure_ascii=False, indent=2)+'\n')
def uid(name): return uuid.uuid5(uuid.NAMESPACE_URL, 'nz-electricity-phase6/'+name).hex[:20]
def tag(name): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'nz-electricity-phase6/'+name))
def q(s): return "'"+s.replace("'", "''")+"'"
def schema(kind): return BASE+f'item/report/definition/{kind}/{VERSIONS[kind]}/schema.json'

def columns():
    result=read(ROOT/'outputs/powerbi/source_validation.json')['columns']
    result['DimDate']=[{'name':n,'postgres_type':t} for n,t in [
        ('Date','date'),('Year','int8'),('Month Number','int8'),('Month','text'),
        ('Year-Month','text'),('Year-Month Sort','int8'),('Quarter','text'),
        ('Weekday Number','int8'),('Weekday','text'),('Day Type','text')]]
    result['DimMonth']=[{'name':n,'postgres_type':t} for n,t in [('Year-Month','text'),('Year-Month Sort','int8'),('MonthStart','date')]]
    result['CaseContext']=[{'name':n,'postgres_type':'text'} for n in
        ['case_id','event_id','selection_reason','publisher','title','url','locator','supported_context','qualification','review_date']]
    return result

def model():
    types={'int8':'int64','int4':'int64','numeric':'double','float8':'double','bool':'boolean','date':'dateTime','timestamp':'dateTime','text':'string'}
    cols=columns(); measures=read(P/'measure_catalog.json')
    write(MODEL/'definition/database.tmdl','database\n\tcompatibilityLevel: 1600\n')
    write(MODEL/'definition/model.tmdl', 'model Model\n\tculture: en-NZ\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-NZ\n\n\tannotation PBI_QueryOrder = '+json.dumps([x.stem for x in sorted((P/'queries').glob('*.pq'))])+'\n\n\tannotation __PBI_TimeIntelligenceEnabled = 0\n')
    expressions=[]
    for name in ['pServer','pDatabase','Source','ReleaseGate']:
        expressions += [f'expression {name} =', *['\t\t'+x for x in (P/'queries'/f'{name}.pq').read_text(encoding='utf-8-sig').splitlines()], '\tlineageTag: '+tag(name),'']
    write(MODEL/'definition/expressions.tmdl','\n'.join(expressions).rstrip()+'\n')
    for table, fields in cols.items():
        lines=[f'table {q(table)}', '\tlineageTag: '+tag(table)]
        if table=='DimDate': lines+=['\tdataCategory: Time']
        if table=='EventInterval': lines+=['\tisHidden']
        for c in fields:
            n,t=c['name'],c['postgres_type']
            lines+=['',f'\tcolumn {q(n)}',f'\t\tdataType: {types[t]}',f'\t\tsourceColumn: {n}', '\t\tsummarizeBy: none','\t\tlineageTag: '+tag(table+'.'+n)]
            hidden=(table in ['FactNational','FactZone'] and n!='is_price_pressure') or table in ['EventInterval','RegionalSignal'] or n in ['interval_id','Year-Month Sort','Month Number','Weekday Number'] or (table=='Events' and t in ['numeric','float8','int8','int4'])
            if hidden: lines+=['\t\tisHidden']
            if table=='DimDate' and n=='Date': lines+=['\t\tisKey']
            sorts={'Month':'Month Number','Year-Month':'Year-Month Sort','Weekday':'Weekday Number'}
            if table in ['DimDate','DimMonth'] and n in sorts: lines+=['\t\tsortByColumn: '+q(sorts[n])]
            if t=='date': lines+=['\t\tformatString: yyyy-MM-dd','\t\tannotation UnderlyingDateTimeDataType = Date']
            elif t=='timestamp': lines+=['\t\tformatString: yyyy-MM-dd HH:mm']
            elif t in ['int8','int4']: lines+=['\t\tformatString: 0']
            if n in ['url','evidence_url']: lines+=['\t\tdataCategory: WebUrl']
        for m in measures:
            if m['home_table']!=table: continue
            lines+=['',f'\tmeasure {q(m["name"])} =',*['\t\t\t'+s for s in m['expression'].splitlines()], '\t\tformatString: '+(m['format_string'] or '""'), '\t\tdisplayFolder: '+m['display_folder'],'\t\tlineageTag: '+tag('measure.'+m['name'])]
        lines+=['',f'\tpartition {q(table)} = m','\t\tmode: import','\t\tsource =',*['\t\t\t\t'+s for s in (P/'queries'/f'{table}.pq').read_text(encoding='utf-8-sig').splitlines()]]
        write(MODEL/'definition/tables'/f'{table}.tmdl','\n'.join(lines)+'\n')
    lines=[]
    for r in read(P/'relationships.json'):
        lines += ['relationship '+tag(str(r)),f'\tfromColumn: {q(r["many_table"])}.{q(r["many_column"])}',f'\ttoColumn: {q(r["one_table"])}.{q(r["one_column"])}','\tfromCardinality: many','\ttoCardinality: one','\tcrossFilteringBehavior: oneDirection','']
    write(MODEL/'definition/relationships.tmdl','\n'.join(lines))
    out(MODEL/'definition.pbism',{'$schema':BASE+'item/semanticModel/definitionProperties/1.0.0/schema.json','version':'4.0','settings':{}})

def field(table, column, measure=False):
    return {'Measure' if measure else 'Column':{'Expression':{'SourceRef':{'Entity':table}},'Property':column}}
def m(name): return field('FactNational',name,True)
def literal(value):
    v=('true' if value else 'false') if isinstance(value,bool) else str(value)+'D' if isinstance(value,(float,int)) else q(value)
    return {'expr':{'Literal':{'Value':v}}}
def obj(**props): return [{'properties':{k:literal(v) for k,v in props.items()}}]
def filt(table,col,values,measure=False):
    f=field(table,col,measure); f[next(iter(f))]['Expression']['SourceRef']={'Source':'s'}
    vals=[[{'Literal':{'Value':q(v) if isinstance(v,str) else str(v)+'L'}}] for v in values]
    return {'Version':2,'From':[{'Name':'s','Entity':table,'Type':0}], 'Where':[{'Condition':{'In':{'Expressions':[f],'Values':vals}}}]}
def filter_entry(table,col,values,measure=False):
    return {'name':uid(table+col+str(values)), 'field':field(table,col,measure),'type':'Categorical','filter':filt(table,col,values,measure),'howCreated':'User'}

class ReportBuilder:
    def __init__(self):
        self.pages=read(P/'page_specification.json'); self.records=[]; self.current=[]; self.bookmarks=[]
    def visual(self,key,kind,rect,title='',roles=None,filters=None,hidden=False):
        x,y,w,h=rect; name=uid(key)
        visual={'visualType':kind,'drillFilterOtherVisuals':True,'visualContainerObjects':{'title':obj(show=bool(title),text=title,fontSize=11,titleWrap=True),'background':obj(show=True,transparency=0)}}
        if roles:
            state={}
            for role,fs in roles.items():
                state[role]={'projections':[{'field':f,'queryRef':f'{next(iter(f.values()))["Expression"]["SourceRef"]["Entity"]}.{next(iter(f.values()))["Property"]}'} for f in fs]}
            visual['query']={'queryState':state}
        v={'$schema':schema('visualContainer'),'name':name,'position':{'x':x,'y':y,'z':len(self.current),'width':w,'height':h,'tabOrder':len(self.current)},'visual':visual,'annotations':[{'name':'ApprovedLayout','value':key}]}
        if filters: v['filterConfig']={'filters':filters}
        if hidden: v['isHidden']=True
        self.current.append((key,v)); return v
    def text(self,key,rect,text):
        v=self.visual(key,'textbox',rect)
        v['visual']['objects']={'general':[{'properties':{'paragraphs':[{'textRuns':[{'value':text,'textStyle':{'fontFamily':'Segoe UI','fontSize':'12pt','color':'#172B3A'}}]}]}}]}
        return v
    def button(self,key,rect,label,action,target):
        v=self.visual(key,'actionButton',rect)
        v['visual']['objects']={'text':obj(show=True,text=label,fontSize=10)}
        props={'show':True,'type':action}
        props[{'Bookmark':'bookmark','PageNavigation':'navigationSection','Drillthrough':'drillthroughSection'}.get(action,'navigationSection')]=target
        v['visual']['visualContainerObjects']['visualLink']=obj(**props)
        return v
    def bookmark(self,name,page,states,display=False):
        b={'$schema':schema('bookmark'),'name':uid('bookmark.'+name),'displayName':name,'options':{'applyOnlyToTargetVisuals':True,'targetVisualNames':list(states),'suppressActiveSection':display,'suppressData':display,'suppressDisplay':not display},'explorationState':{'version':'1.3','activeSection':page,'sections':{page:{'visualContainers':states}}}}
        self.bookmarks.append(b); return b['name']
    def build(self):
        known=filter_entry('DimZone','zone',['UNI','CNI','LNI','USI','LSI'])
        for page in self.pages:
            n=page['number']; pageid=uid(f'page{n}'); self.current=[]
            self.text(f'{n}.heading',[28,10,760,38],page['title'])
            self.text(f'{n}.qualifier',[28,48,760,30],page['qualifier'])
            for j,p in enumerate(self.pages): self.button(f'{n}.nav{j}',[28+j*196,83,190,28],p['title'],'PageNavigation',uid(f'page{j+1}'))
            if n<=3:
                v=self.visual(f'{n}.date','slicer',[1008,10,244,64],'NZ trading dates',{'Values':[field('DimDate','Date')]})
                v['visual']['objects']={'data':obj(mode='Between')}; v['visual']['syncGroup']={'groupName':'LocalTradingDate','fieldChanges':True,'filterChanges':True}
            for spec in page['visuals']:
                key=spec['id']; rect=spec['rect']; vals=spec['values']; title=spec['title']; typ=spec['type']
                if typ=='Card group':
                    for i,value in enumerate(vals):
                        self.visual(key+f'.{i+1}','card',[rect[0]+i*rect[2]/len(vals),rect[1],rect[2]/len(vals)-4,rect[3]],value,{'Values':[m(value)]})
                    continue
                if typ.startswith('Text'):
                    text={'P1.7':'March sustained exposure and August extreme-tail risk are different patterns. Fixed P99 uses the complete Sep 2025–Aug 2026 release.',
                          'P3.6':'Absolute generation and mix shares answer different questions. Renewable share excludes Storage and Unclassified. Matched demand benchmark uses the full release; associations are not causal.',
                          'P5.7':'37 selected publications. Prices are weighted ratios; P99 is fixed for the full release. Unknown geography and invalid NSP quarantine remain visible. Historical data remain revision-eligible; findings describe associations.'}.get(key,title)
                    self.text(key,rect,text); continue
                if key=='P4.1':
                    v=self.visual(key+'.selector','slicer',[rect[0],rect[1],610,rect[3]],'Event ID',{'Values':[field('Events','event_id')]})
                    v['visual']['objects']={'data':obj(mode='Dropdown'),'selection':obj(singleSelect=True,selectAllCheckboxEnabled=False)}
                    ids=['National:National:202608040730','National:National:202509051930','Zone:CNI:202603021830','National:National:202608040630','National:National:202603291430']
                    for i,event in enumerate(ids+[None]):
                        label='E'+str(i+1) if event else 'Reset event'
                        state={'singleVisual':{'objects':{'merge':{'general':[{'properties':{'filter':filt('Events','event_id',[event]) if event else {'Version':2,'From':[{'Name':'s','Entity':'Events','Type':0}],'Where':[]}}}]}}}}
                        b=self.bookmark(label,pageid,{v['name']:state})
                        self.button(key+'.'+label,[650+i*100,rect[1]+20,96,32],label,'Bookmark',b)
                    continue
                self.content(spec,known)
            if n==2:
                v=self.visual('2.zone','slicer',[1010,10,240,65],'Known Zone',{'Values':[field('DimZone','zone')]},[known]); v['visual']['objects']={'data':obj(mode='Dropdown'),'selection':obj(singleSelect=True)}
                # Full-release event browser has independent selectors.
                self.visual('2.eventzone','slicer',[28,742,220,48],'Event Zone',{'Values':[field('Events','zone')]})
                self.visual('2.eventdate','slicer',[260,742,360,48],'Event start (full release)',{'Values':[field('Events','start_date')]})
                self.button('2.drill',[1010,750,240,35],'Investigate selected event','Drillthrough',uid('page4'))
            if n==4:
                self.button('4.back',[1150,83,100,28],'Back','Back','')
                self.visual('4.status','card',[28,111,600,18],'',{'Values':[m('Event Selection Status')]})
            if n==5:
                self.visual('5.month','slicer',[800,10,210,65],'Source month',{'Values':[field('DimMonth','Year-Month')]})
                self.visual('5.source','slicer',[1015,10,235,65],'Source',{'Values':[field('SourceQuality','source_name')]})
                for stem,label in [('P5.6','Classification reference'),('P5.7','Source manifest')]:
                    original=next(v for k,v in self.current if k==stem)
                    rect=[original['position'][a] for a in ['x','y','width','height']]
                    fields=[field('Classification',c) for c in ['fuel_code','tech_code','energy_status','generation_role','review_status','rationale','evidence_url']] if stem=='P5.6' else [field('Release','input_manifest')]
                    alternate=self.visual(stem+'.detail','tableEx',rect,label,{'Values':fields},hidden=True)
                    for show in [False,True]:
                        states={original['name']:{'singleVisual':{'display':{'mode':'hidden' if show else 'elevation'}}},alternate['name']:{'singleVisual':{'display':{'mode':'elevation' if show else 'hidden'}}}}
                        b=self.bookmark(label if show else 'Return '+stem,pageid,states,True)
                        self.button(stem+f'.toggle{show}',[rect[0]+(160 if show else 0),rect[1]+rect[3]-26,156,24],label if show else 'Summary','Bookmark',b)
            interactions=[]
            for sk,sv in self.current:
                for tk,tv in self.current:
                    if sk==tk: continue
                    allow=self.interacts(n,sk,tk)
                    interactions.append({'source':sv['name'],'target':tv['name'],'type':'DataFilter' if allow else 'NoFilter'})
            data={'$schema':schema('page'),'name':pageid,'displayName':page['title'],'displayOption':'FitToPage','width':1280,'height':800,'visualInteractions':interactions}
            if n==4:
                data['pageBinding']={'name':uid('drillEvent'),'type':'Drillthrough','referenceScope':'Default','parameters':[{'name':uid('eventparam'),'fieldExpr':field('Events','event_id')}],'acceptsFilterContext':'None'}
            out(REPORT/'definition/pages'/pageid/'page.json',data)
            for key,v in self.current:
                out(REPORT/'definition/pages'/pageid/'visuals'/v['name']/'visual.json',v)
                self.records.append({'layout':key,'page':pageid,'visual':v['name'],'type':v['visual']['visualType']})
        out(REPORT/'definition/pages/pages.json',{'$schema':schema('pagesMetadata'),'pageOrder':[uid(f'page{i}') for i in range(1,6)],'activePageName':uid('page1')})
        for b in self.bookmarks: out(REPORT/'definition/bookmarks'/f'{b["name"]}.bookmark.json',b)
        out(REPORT/'definition/bookmarks/bookmarks.json',{'$schema':schema('bookmarksMetadata'),'items':[{'name':b['name']} for b in self.bookmarks]})
        out(P/'native_visual_map.json',self.records)

    def content(self,s,known):
        k=s['id']; r=s['rect']; title=s['title']; vals=s['values']; filters=[]; roles={}; kind='tableEx'
        if k in ['P1.3','P1.4','P1.5','P3.2','P3.3','P5.6']:
            kind={'P1.4':'clusteredColumnChart','P1.5':'clusteredColumnChart','P3.2':'columnChart'}.get(k,'lineChart')
            roles={'Category':[field('DimDate','Year-Month')],'Y':[m(v) for v in vals]}
        elif k=='P2.3':
            kind='clusteredBarChart'; roles={'Category':[field('DimZone','zone')],'Y':[m(v) for v in vals]}; filters=[known]
        elif k in ['P2.4','P2.6']:
            kind='lineChart' if k=='P2.4' else 'clusteredColumnChart'; roles={'Category':[field('DimDate','Date')],'Y':[m(v) for v in vals]}
            if k=='P2.4': roles['Tooltips']=[m('Spread Eligible Half-hours')]
        elif k=='P1.6': roles={'Values':[m(v) for v in vals]}
        elif k=='P2.5': roles={'Values':[field('DimZone','zone')]+[m(v) for v in vals]}; filters=[known]
        elif k=='P2.7':
            roles={'Values':[field('Events',c) for c in ['event_id','scope','zone','local_start','local_end']]+[m(v) for v in ['Event Duration','Event Weighted Price','Peak Event Price']]}; filters=[filter_entry('Events','scope',['Zone'])]
        elif k=='P3.4': roles={'Values':[field('FactNational','is_price_pressure')]+[m(v) for v in vals]}
        elif k=='P4.3':
            kind='lineChart'; roles={'Category':[field('DimInterval','start_utc')],'Y':[m('Event Interval Price')],'Tooltips':[field('DimInterval',c) for c in ['local_start','trading_period','fold']]}; filters=[filter_entry('FactNational','Event Interval Visible',[1],True)]
        elif k=='P4.4':
            kind='pivotTable'; roles={'Rows':[field('DimInterval','start_utc')],'Columns':[field('DimZone','zone')],'Values':[m('Zone Pressure Flag')]}; filters=[known,filter_entry('FactNational','Event Interval Visible',[1],True)]
        elif k=='P4.6': roles={'Values':[field('Events',c) for c in ['event_id','scope','zone','local_start','local_end','start_utc','end_utc']]}
        elif k=='P4.7': roles={'Values':[field('CaseContext',c) for c in ['publisher','title','locator','url','supported_context','qualification','review_date']]}
        elif k=='P5.2': roles={'Values':[field('Release',c) for c in ['refresh_id','dq_run_id','dq_as_of_date','input_fingerprint','is_current']]}
        elif k=='P5.3': kind='pivotTable'; roles={'Rows':[field('SourceQuality',c) for c in ['source_name','denominator_unit']],'Columns':[field('DimMonth','Year-Month')],'Values':[m('Source Geography Coverage')]}
        elif k=='P5.4': roles={'Values':[field('SourceQuality',c) for c in ['source_name','source_month','denominator_unit']]+[m('Unknown Source Quantity')]}
        elif k=='P5.5': roles={'Values':[field('DQResults',c) for c in ['rule_id','result_status','affected_rows','expected_value','rule_snapshot','details']]}; filters=[filter_entry('DQResults','result_status',['WARN'])]
        else: raise ValueError('Unencoded approved container: '+k+' '+s['type'])
        v=self.visual(k,kind,r,title,roles,filters)
        if kind in ['tableEx','pivotTable']: v['visual']['objects']={'total':obj(totals=False),'subTotals':obj(rowSubtotals=False,columnSubtotals=False),'columnHeaders':obj(wordWrap=True),'values':obj(wordWrap=True)}
        if k=='P2.3': v['visual']['query']['queryState']['Tooltips']={'projections':[{'field':m('Zone Priced Offtake Coverage'),'queryRef':'FactNational.Zone Priced Offtake Coverage'}]}
        if kind in ['lineChart','clusteredColumnChart','columnChart']:
            v['visual']['objects']={'categoryAxis':obj(axisType='Categorical')}
            v['visual']['query']['sortDefinition']={'sort':[{'field':roles['Category'][0],'direction':'Ascending'}]}

    @staticmethod
    def interacts(n,source,target):
        if source.endswith('.date'): return target.startswith(f'P{n}.') and target not in ['P2.7','P3.5']
        if n==1: return source in ['P1.3','P1.4','P1.5'] and target=='P1.6'
        if n==2:
            if source in ['2.zone','P2.3','P2.5']: return target in ['P2.3','P2.5']
            if source in ['2.eventzone','2.eventdate']: return target=='P2.7'
        if n==4: return source=='P4.1.selector' and (target.startswith('P4.') or target=='4.status')
        if n==5: return source in ['5.month','5.source'] and target in ['P5.3','P5.4']
        return False

def build():
    model(); ReportBuilder().build()
    out(P/'NZ_Electricity_Market.pbip',{'$schema':BASE+'pbip/pbipProperties/1.0.0/schema.json','version':'1.0','artifacts':[{'report':{'path':REPORT.name}}],'settings':{'enableAutoRecovery':True}})
    out(REPORT/'definition.pbir',{'$schema':BASE+'item/report/definitionProperties/2.0.0/schema.json','version':'4.0','datasetReference':{'byPath':{'path':'../'+MODEL.name}}})
    out(REPORT/'definition/version.json',{'$schema':schema('versionMetadata'),'version':'2.0.0'})
    out(REPORT/'definition/report.json',{'$schema':schema('report'),'themeCollection':{'customTheme':{'name':'NZ_Electricity','reportVersionAtImport':{'visual':'2.12.0','page':'2.1.0','report':'3.3.0'},'type':'RegisteredResources'}},'resourcePackages':[{'name':'RegisteredResources','type':'RegisteredResources','items':[{'name':'NZ_Electricity','path':'NZ_Electricity.json','type':'CustomTheme'}]}],'settings':{'defaultFilterActionIsDataFilter':True,'useCrossReportDrillthrough':False,'useEnhancedTooltips':True,'defaultDisplayUnitsToNone':True}})
    write(REPORT/'StaticResources/RegisteredResources/NZ_Electricity.json',(P/'theme.json').read_text(encoding='utf-8'))
    inputs=sorted((P/'queries').glob('*.pq'))+[P/x for x in ['measure_catalog.json','measures.dax','relationships.json','page_specification.json','case_presets.json','theme.json']]
    out(P/'native_input_hashes.json',{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs})
    print('Generated native sources; Desktop acceptance remains pending.')

if __name__=='__main__': build()
