"""Targeted repairs for observed 16 October Desktop defects; no regeneration.

Run with Desktop closed. Preserves imported model, IDs and approved DAX/M.
"""
from build_native_project import P, REPORT, read, out, field, filt, literal, obj, uid

def color(value): return {'solid':{'color':literal(value)}}

def repair():
    mapping=read(P/'native_visual_map.json')
    bykey={r['layout']:REPORT/'definition/pages'/r['page']/'visuals'/r['visual']/'visual.json' for r in mapping}
    for key,path in bykey.items():
        v=read(path); visual=v['visual']; pos=v['position']
        objects=visual.setdefault('objects',{})
        vc=visual.setdefault('visualContainerObjects',{})
        # Explicit contrasting title color, independent of Desktop dark chrome.
        for entry in vc.get('title',[]): entry['properties']['fontColor']=color('#172B3A')
        if visual['visualType']=='actionButton':
            old=objects['text'][0]['properties']; label=old.get('text')
            if label is None:
                label=next(x['properties']['text'] for x in objects['text'] if 'text' in x['properties'])
            objects['text']=obj(show=True)+[{'selector':{'id':'default'},'properties':{'text':label,'fontSize':literal(9),'fontColor':color('#FFFFFF'),'horizontalAlignment':literal('center')}}]
            objects['icon']=obj(show=False)+[{'selector':{'id':'default'},'properties':{'placement':literal('left')}}]
            objects['fill']=obj(show=True)+[{'selector':{'id':'default'},'properties':{'fillColor':color('#12647A')}}]
            objects['outline']=obj(show=False)
            objects['shape']=obj(tileShape='rectangle')
            vc['background']=obj(show=False); vc['border']=obj(show=False)
            pos['height']=40
            if '.nav' in key or key=='4.back': pos['y']=78
            if key.startswith('P4.1.') and key!='P4.1.selector': pos['y']=136
            if '.toggle' in key:
                spec=next(s for p in read(P/'page_specification.json') for s in p['visuals'] if s['id']==key.split('.toggle')[0])
                pos['y']=spec['rect'][1]+spec['rect'][3]-40
        if visual['visualType']=='card':
            objects['labels']=obj(fontSize=23)
            objects['categoryLabels']=obj(show=False)
        if visual['visualType']=='slicer':
            objects['header']=obj(show=False)
            vc['title'][0]['properties']['fontSize']=literal(10)
            pos['height']=70
            if key.endswith('.date'): pos.update(x=950,y=2,width=302,height=74)
            if key=='2.zone': pos.update(x=710,y=2,width=220,height=74)
            if key in ['5.month','5.source','2.zone','2.eventzone','P4.1.selector']: objects['data']=obj(mode='Dropdown')
            if key=='2.eventzone':pos.update(x=28,y=724,width=220,height=70)
            if key=='2.eventdate':pos.update(x=260,y=724,width=360,height=70);objects['data']=obj(mode='Between')
            if key=='P4.1.selector':pos.update(x=28,y=122,width=610,height=64)
        if key=='P2.7': pos['height']=90
        if key=='4.status':
            pos.update(x=650,y=10,width=600,height=35)
            objects['labels']=obj(fontSize=12)
        if key in ['P4.3','P4.4']:
            # Measure filters are Advanced comparisons, not categorical IN.
            # Aggregate detail tooltips at the UTC axis grain: raw tooltip
            # columns otherwise become extra grouping projections.
            if key=='P4.3':
                for projection in visual['query']['queryState']['Tooltips']['projections']:
                    if 'Column' in projection['field']:
                        projection['field']={'Aggregation':{'Expression':projection['field'],'Function':3}}
                        projection['queryRef']='Min('+projection['queryRef']+')'
            filters=[f for f in v.get('filterConfig',{}).get('filters',[]) if 'filter' in f and 'Measure' not in f.get('field',{})]
            measure=field('FactNational','Event Interval Visible',True)
            target=field('FactNational','Event Interval Visible',True)
            target['Measure']['Expression']['SourceRef']={'Source':'s'}
            filters.append({'name':uid('visibleComparison'),'field':measure,'type':'Advanced','howCreated':'User','filter':{'Version':2,'From':[{'Name':'s','Entity':'FactNational','Type':0}], 'Where':[{'Condition':{'Comparison':{'ComparisonKind':0,'Left':target,'Right':{'Literal':{'Value':'1L'}}}}}]}})
            v['filterConfig']={'filters':filters}
        out(path,v)
    # Slicer bookmark property is a Filter object wrapper; bare Version/From
    # was silently dropped by Desktop's save serializer.
    ids=['National:National:202608040730','National:National:202509051930','Zone:CNI:202603021830','National:National:202608040630','National:National:202603291430']
    for name,event in [(f'E{i+1}',v) for i,v in enumerate(ids)]+[('Reset event',None)]:
        path=REPORT/'definition/bookmarks'/f'{uid("bookmark."+name)}.bookmark.json';b=read(path)
        state=b['explorationState']['sections'][uid('page4')]['visualContainers'][uid('P4.1.selector')]
        f=filt('Events','event_id',[event]) if event else {'Version':2,'From':[{'Name':'s','Entity':'Events','Type':0}],'Where':[]}
        state['singleVisual']['objects']={'merge':{'general':[{'properties':{'filter':{'filter':f}}}]}}
        out(path,b)
    path=REPORT/'definition/pages'/uid('page4')/'page.json';page=read(path)
    name=uid('drillEventFilter')
    page['filterConfig']={'filters':[{'name':name,'field':field('Events','event_id'),'type':'Categorical','howCreated':'Drillthrough'}]}
    page['pageBinding']['parameters']=[{'name':uid('eventparam'),'boundFilter':name}]
    out(path,page)
    print('Applied targeted runtime repairs; Desktop revalidation required.')

if __name__=='__main__': repair()
