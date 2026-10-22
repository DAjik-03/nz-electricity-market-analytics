"""Offline Microsoft JSON schema validation plus approved model/report contracts."""
import hashlib
import json
from pathlib import Path
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7
from build_native_project import P, ROOT, REPORT, MODEL, columns, read
from fetch_pbip_schemas import CACHE

def validate():
    index=read(CACHE/'index.json')
    registry=Registry()
    for url,meta in index.items():
        path=CACHE/meta['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256']
        registry=registry.with_resource(url,Resource.from_contents(read(path),default_specification=DRAFT7))
    paths=[P/'NZ_Electricity_Market.pbip',MODEL/'definition.pbism',REPORT/'definition.pbir']+list((REPORT/'definition').rglob('*.json'))
    errors=[]
    unavailable=[]
    # Desktop 2.159 emits this version; its public endpoint returned HTTP 404
    # on 2026-10-21. Do not substitute an older schema or rewrite the report.
    known_unpublished='https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.14.0/schema.json'
    for path in paths:
        doc=read(path); url=doc.get('$schema')
        if not url:
            suffixes={'.pbip':'pbip/pbipProperties/1.0.0/schema.json','.pbism':'item/semanticModel/definitionProperties/1.0.0/schema.json','.pbir':'item/report/definitionProperties/2.0.0/schema.json'}
            url='https://developer.microsoft.com/json-schemas/fabric/'+suffixes[path.suffix]
            doc={'$schema':url,**doc}
        if url == known_unpublished and url not in index:
            unavailable.append(str(path.relative_to(P)))
            continue
        validator=Draft7Validator(registry.contents(url),registry=registry)
        for e in validator.iter_errors(doc): errors.append(f'{path.relative_to(P)} {list(e.path)}: {e.message}')
    if errors: raise ValueError('\n'.join(errors))
    cols={t:{c['name'] for c in cs} for t,cs in columns().items()}
    measures=read(P/'measure_catalog.json'); names={m['name'] for m in measures}
    assert len(measures)==len(names)==59 and len(cols)==16
    def refs(v):
        if isinstance(v,dict):
            for kind in ['Column','Measure']:
                f=v.get(kind)
                if isinstance(f,dict) and 'Property' in f:
                    table=f.get('Expression',{}).get('SourceRef',{}).get('Entity')
                    if table:
                        assert table in cols,table
                        assert f['Property'] in (names if kind=='Measure' else cols[table]), (table,f['Property'])
            for child in v.values(): refs(child)
        elif isinstance(v,list):
            for child in v: refs(child)
    for path in paths: refs(read(path))
    rels=read(P/'relationships.json'); assert len(rels)==8
    for r in rels:
        assert r['one_column'] in cols[r['one_table']] and r['many_column'] in cols[r['many_table']]
        assert r['direction']=='single' and r['active']
        assert r['one_table'] not in ['FactNational','FactZone','EventInterval','Threshold','DemandBenchmark']
        assert r['many_table'] not in ['Threshold','DemandBenchmark']
    mapping=read(P/'native_visual_map.json'); ids=[r['visual'] for r in mapping]
    assert len(ids)==len(set(ids))
    layouts={r['layout'].split('.')[0]+'.'+r['layout'].split('.')[1] for r in mapping if r['layout'].startswith('P')}
    assert len(layouts)==34,len(layouts)
    for file,digest in read(P/'native_input_hashes.json').items():
        assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==digest,file
    result={'json_files_validated':len(paths)-len(unavailable),'json_files_reference_checked':len(paths),'schema_documents':len(index),'schema_status':'PARTIAL_PUBLIC_SCHEMA_UNAVAILABLE' if unavailable else 'PASS','unavailable_schema_files':unavailable,'unavailable_schema_url':known_unpublished if unavailable else None,'tables':16,'connection_only':4,'relationships':8,'measures':59,'pages':5,'approved_layout_containers':34,'native_visuals':len(ids),'desktop_acceptance':'SEPARATE_RUNTIME_EVIDENCE_REQUIRED'}
    dest=ROOT/'outputs/powerbi/native_static_validation.json'; dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    (P/'native_schema_hashes.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2)); return result

if __name__=='__main__': validate()
