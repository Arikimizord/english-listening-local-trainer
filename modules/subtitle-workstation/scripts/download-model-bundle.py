"""Download immutable named model assets and verify against the repository manifest."""
import pathlib,json,hashlib,urllib.request,subprocess,sys,os
ROOT=pathlib.Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'config/model-bundle-v1.json').read_text(encoding='utf-8-sig'))
dest=ROOT/'cache/model-bundle';dest.mkdir(parents=True,exist_ok=True)
base='https://github.com/Arikimizord/english-listening-local-trainer/releases/download/'+manifest['tag']+'/'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for item in manifest['parts']:
 p=dest/item['name']
 if p.exists() and p.stat().st_size==item['bytes'] and sha(p)==item['sha256']:continue
 partial=p.with_name(p.name+'.partial');offset=partial.stat().st_size if partial.exists() else 0
 if offset>item['bytes']:raise RuntimeError('Oversized partial model asset')
 if offset<item['bytes']:
  headers={'User-Agent':'english-listening-local-trainer'}
  if offset:headers['Range']='bytes='+str(offset)+'-'
  with urllib.request.urlopen(urllib.request.Request(base+item['name'],headers=headers),timeout=180) as response:
   if offset and response.status==206:assert response.headers.get('Content-Range','').startswith('bytes '+str(offset)+'-');mode='ab'
   else:assert response.status==200;mode='wb'
   print('Downloading',item['name'],flush=True)
   with partial.open(mode) as target:
    while chunk:=response.read(8*1024**2):target.write(chunk)
 if partial.stat().st_size!=item['bytes'] or sha(partial)!=item['sha256']:raise RuntimeError('Model asset checksum mismatch; do not bypass verification: '+item['name'])
 os.replace(partial,p)
subprocess.run([sys.executable,'-I','-B','-X','utf8',str(ROOT/'scripts/install-model-bundle.py'),'--directory',str(dest)],check=True)
