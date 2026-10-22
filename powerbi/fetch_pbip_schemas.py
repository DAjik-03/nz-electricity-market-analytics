"""Cache version-pinned Microsoft schemas and their references; no data access."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin, urldefrag
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'outputs/local/phase6c/schema_cache'
BASE = 'https://developer.microsoft.com/json-schemas/fabric/item/report/'
VERSIONS = {'visualContainer':'2.12.0','page':'2.1.0','report':'3.3.0',
            'bookmark':'2.1.0','bookmarksMetadata':'1.0.0',
            'pagesMetadata':'1.1.0','versionMetadata':'1.0.0'}
URLS = [BASE+f'definition/{k}/{v}/schema.json' for k,v in VERSIONS.items()] + [
    BASE+'definitionProperties/2.0.0/schema.json',
    'https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json',
    'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json']

def references(value):
    if isinstance(value,dict):
        if '$ref' in value: yield value['$ref']
        for child in value.values(): yield from references(child)
    elif isinstance(value,list):
        for child in value: yield from references(child)

def fetch():
    CACHE.mkdir(parents=True,exist_ok=True)
    pending=list(URLS); seen={}
    for path in (ROOT/'powerbi/NZ_Electricity_Market.Report/definition').rglob('*.json'):
        declared=json.loads(path.read_text(encoding='utf-8')).get('$schema')
        if declared: pending.append(declared)
    while pending:
        url=urldefrag(pending.pop())[0]
        if url in seen: continue
        assert url.startswith('https://developer.microsoft.com/json-schemas/'),url
        path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if not path.exists():
            with urlopen(url,timeout=60) as response: path.write_bytes(response.read())
        content=path.read_bytes(); schema=json.loads(content)
        seen[url]={'file':path.name,'sha256':hashlib.sha256(content).hexdigest()}
        pending.extend(urljoin(url,ref) for ref in references(schema) if not ref.startswith('#'))
    (CACHE/'index.json').write_text(json.dumps(seen,indent=2)+'\n',encoding='utf-8')
    print(f'Cached {len(seen)} Microsoft schema documents')
    return seen

if __name__=='__main__': fetch()
