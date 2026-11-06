"""Install the pinned split archive; only declared model/resource entries are copied."""
import argparse,pathlib,json,hashlib,zipfile,tempfile,shutil,os
ROOT=pathlib.Path(__file__).resolve().parents[1]
def digest(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);parser.add_argument('--verify-only',action='store_true');args=parser.parse_args()
 manifest=json.loads((ROOT/'config/model-bundle-v1.json').read_text(encoding='utf-8-sig'));directory=pathlib.Path(args.directory).resolve()
 lock=json.loads((ROOT/'config/models-stage3.lock.json').read_text(encoding='utf-8-sig'))
 expected={m['directory']+'/'+f['name']:f for m in lock['models'] for f in m['files']}
 expected.update({f['destination']:f for f in lock['resources'] if f['destination'].startswith('models/resources/')})
 declared={f['path']:f for f in manifest['files']};assert set(expected)==set(declared),'Bundle file list differs from model lock'
 (ROOT/'temp').mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='model-bundle-',dir=ROOT/'temp') as work:
  archive=pathlib.Path(work)/'models.zip';whole=hashlib.sha256();total=0
  with archive.open('wb') as target:
   for part in manifest['parts']:
    path=directory/part['name'];assert path.stat().st_size==part['bytes'],'Wrong part size: '+path.name
    h=hashlib.sha256()
    with path.open('rb') as source:
     while chunk:=source.read(8*1024**2):h.update(chunk);whole.update(chunk);target.write(chunk);total+=len(chunk)
    assert h.hexdigest()==part['sha256'],'Wrong part hash: '+path.name
  assert total==manifest['archive_bytes'] and whole.hexdigest()==manifest['archive_sha256'],'Wrong archive checksum'
  with zipfile.ZipFile(archive) as z:
   names=z.namelist();assert len(names)==len(set(names)),'Duplicate archive entry'
   assert set(names)==set(expected)|{'MODEL-SOURCES.json','MODEL-LICENSES/APACHE-2.0.txt','MODEL-LICENSES/OPENAI-WHISPER-MIT.txt'},'Unexpected archive entry'
   for name,f in expected.items():
    assert z.getinfo(name).file_size==f['size'];dest=ROOT/name;staged=pathlib.Path(work)/name;staged.parent.mkdir(parents=True,exist_ok=True)
    h=hashlib.sha256();git=hashlib.sha1(f"blob {f['size']}\0".encode())
    with z.open(name) as source,staged.open('wb') as target:
     while chunk:=source.read(8*1024**2):h.update(chunk);git.update(chunk);target.write(chunk)
    assert h.hexdigest()==declared[name]['sha256'],name
    assert h.hexdigest()==f['sha256'] if f.get('sha256') else git.hexdigest()==f['git_blob_sha1'],name
    if not args.verify_only:dest.parent.mkdir(parents=True,exist_ok=True);os.replace(staged,dest)
   if not args.verify_only:
    for name in names:
     if name.startswith('MODEL-LICENSES/'):
      dest=ROOT/'models/licenses'/pathlib.Path(name).name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
    with zipfile.ZipFile(ROOT/'models/resources/punkt_tab.zip') as nltk:
     for name in nltk.namelist():
      if name.startswith('punkt_tab/english/') and not name.endswith('/') or name=='punkt_tab/README':
       dest=(ROOT/'cache/nltk/tokenizers'/name).resolve();assert dest.is_relative_to((ROOT/'cache/nltk/tokenizers').resolve());dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(nltk.read(name))
 print(json.dumps({'ok':True,'verified_files':len(expected),'installed':not args.verify_only,'model_revision_changed':False}))
if __name__=='__main__':main()
