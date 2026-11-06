"""Stage 3 approved downloads only; pinned revisions and upstream integrity checks."""
import os,pathlib,json,hashlib,urllib.request,time,zipfile,concurrent.futures,shutil
root=pathlib.Path(__file__).resolve().parents[1]
lock=json.loads((root/'config/models-stage3.lock.json').read_text(encoding='utf-8-sig'))
if shutil.disk_usage(root).free<10*1024**3:raise RuntimeError('Need at least 10 GiB free for stage 3')
os.environ['HF_HUB_DISABLE_PROGRESS_BARS']='1'
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
os.environ['HF_XET_CACHE']=str(root/'cache/huggingface/xet')
os.environ['HF_HUB_ETAG_TIMEOUT']='45'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='120'
for key in ['HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE']:os.environ.pop(key,None)
receipt={'schema_version':1,'stage':3,'model_files':[],'resource_files':[],'nltk_extracted_files':[],'uploaded_user_media':False}
def verify(path,entry):
    assert path.stat().st_size==entry['size'],f'Size mismatch: {path}'
    sha=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    if entry.get('sha256'):assert sha==entry['sha256'],f'LFS SHA256 mismatch: {path}'
    else:
        h=hashlib.sha1();h.update(f"blob {entry['size']}\0".encode())
        with path.open('rb') as f:
            while data:=f.read(4*1024**2):h.update(data)
        assert h.hexdigest()==entry['git_blob_sha1'],f'Git blob mismatch: {path}'
    return {'path':str(path.relative_to(root)),'bytes':path.stat().st_size,'sha256':sha,'upstream_integrity':'lfs-sha256' if entry.get('sha256') else 'git-blob-sha1'}
for a in lock['resources']:
    p=root/a['destination'];p.parent.mkdir(parents=True,exist_ok=True)
    good=False
    if p.exists():
        try:record=verify(p,a);good=True
        except Exception:pass
    if not good:
        print('Downloading resource:',a['name'],flush=True)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(a['url'],timeout=90) as src,p.open('wb') as out:
                    while data:=src.read(1024**2):out.write(data)
                record=verify(p,a);break
            except Exception:
                if attempt==2:raise
                time.sleep(2)
    receipt['resource_files'].append(record)
archive=root/'models/resources/punkt_tab.zip';dest=root/'cache/nltk/tokenizers'
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name in z.namelist():
        if (name.startswith('punkt_tab/english/') and not name.endswith('/')) or name=='punkt_tab/README':
            out=(dest/name).resolve()
            assert out.is_relative_to(dest.resolve())
            out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(name))
            receipt['nltk_extracted_files'].append({'path':str(out.relative_to(root)),'bytes':out.stat().st_size,'sha256':hashlib.file_digest(out.open('rb'),'sha256').hexdigest()})
import importlib.util
spec=importlib.util.spec_from_file_location('pinned_download',root/'scripts/download-pinned-model.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def download(m):
    print('Downloading pinned model:',m['repo_id'],m['revision'],flush=True)
    target=root/m['directory']
    target.mkdir(parents=True,exist_ok=True)
    for a in m['files']:
        p=target/a['name'];good=False
        if p.exists():
            try:verify(p,a);good=True
            except Exception:pass
        if good:continue
        if a['size']>64*1024**2:
            module.download_pinned(root,p,a,workers=16)
        else:
            with urllib.request.urlopen(a['url'],timeout=90) as src,p.open('wb') as out:
                while data:=src.read(1024**2):out.write(data)
            verify(p,a)
    files=[verify(target/f['name'],f) for f in m['files']]
    print('Verified model:',m['repo_id'],flush=True)
    return files
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for files in pool.map(download,lock['models']):receipt['model_files'].extend(files)
receipt['ok']=True
receipt['verified_bytes']=sum(x['bytes'] for x in receipt['model_files']+receipt['resource_files'])
(root/'planning/stage3/model-download-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'ok':True,'verified_bytes':receipt['verified_bytes'],'model_files':len(receipt['model_files']),'resource_files':len(receipt['resource_files'])},ensure_ascii=False),flush=True)
