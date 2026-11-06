"""Verified ranged download from the official PyTorch index; resume completed chunks."""
import urllib.request,urllib.parse,html,re,pathlib,json,hashlib,concurrent.futures,time,os
root=pathlib.Path(__file__).resolve().parents[1]
name='torch-2.8.0+cu128-cp311-cp311-win_amd64.whl';index='https://download.pytorch.org/whl/cu128/torch/'
with urllib.request.urlopen(index,timeout=60) as r:page=r.read().decode()
links=[html.unescape(x) for x in re.findall(r'href="([^"]+)"',page)]
link=next(x for x in links if urllib.parse.unquote(urllib.parse.urlsplit(x).path.rsplit('/',1)[-1])==name)
expected=urllib.parse.parse_qs(urllib.parse.urlsplit(link).fragment)['sha256'][0]
assert '--hash=sha256:'+expected in (root/'config/requirements-win-py311.lock').read_text(encoding='utf-8-sig')
index_url=urllib.parse.urljoin(index,link).split('#')[0]
url=index_url.replace('https://download-r2.pytorch.org/','https://download.pytorch.org/')
dest=root/'cache/downloads'/name
req=urllib.request.Request(url+'?workbench-size=1',headers={'Range':'bytes=0-0','Accept-Encoding':'identity'})
with urllib.request.urlopen(req,timeout=60) as r:
    assert r.status==206
    total=int(r.headers['Content-Range'].split('/')[-1]);r.read()
parts=dest.with_suffix('.parts');parts.mkdir(exist_ok=True)
chunk_size=32*1024**2
jobs=[(i,start,min(start+chunk_size,total)-1) for i,start in enumerate(range(0,total,chunk_size))]
def get(job):
    i,start,end=job;p=parts/f'{i:05d}.part';length=end-start+1
    for attempt in range(8):
        done=p.stat().st_size if p.exists() else 0
        if done==length:return length
        if done>length:raise RuntimeError('Unexpected oversized chunk')
        offset=start+done
        try:
            req=urllib.request.Request(url+f'?workbench-range={offset}-{end}',headers={'Range':f'bytes={offset}-{end}','Accept-Encoding':'identity'})
            with urllib.request.urlopen(req,timeout=90) as r:
                assert r.status==206 and r.headers['Content-Range']==f'bytes {offset}-{end}/{total}',dict(r.headers)
                with p.open('ab') as out:
                    while data:=r.read(256*1024):out.write(data);out.flush()
            assert p.stat().st_size==length, f'Incomplete range: {p.stat().st_size}/{length} bytes; resuming'
            return length
        except Exception as e:
            print(f'Part {i} retry {attempt+1}: {type(e).__name__}: {str(e)[:180]}',flush=True)
            if attempt==7:raise
            time.sleep(min(attempt+1,5))
if dest.exists() and dest.stat().st_size==total and hashlib.file_digest(dest.open('rb'),'sha256').hexdigest()==expected:
    print('Wheel already verified',flush=True)
else:
    print(f'Downloading {total} bytes in {len(jobs)} resumable ranges; 32 connections',flush=True)
    completed=0;last=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        for future in concurrent.futures.as_completed([pool.submit(get,j) for j in jobs]):
            completed+=future.result()
            if time.monotonic()-last>15 or completed==total:
                print(f'{completed/total:.1%} ({completed/1024**2:.0f}/{total/1024**2:.0f} MiB)',flush=True);last=time.monotonic()
    h=hashlib.sha256()
    with dest.open('wb') as out:
        for i,_,_ in jobs:
            with (parts/f'{i:05d}.part').open('rb') as src:
                while data:=src.read(4*1024**2):out.write(data);h.update(data)
    assert dest.stat().st_size==total and h.hexdigest()==expected,'Official wheel SHA256 mismatch'
source={'filename':name,'url':url,'sha256':expected,'bytes':total,'source_index':index,'index_download_url':index_url,'hash_in_requirements_lock':True}
(root/'planning/torch-wheel-source.json').write_text(json.dumps(source,indent=2),encoding='utf-8')
# Remove only this downloader's completed chunk files after final wheel verification.
for i,_,_ in jobs:
    p=parts/f'{i:05d}.part'
    if p.exists():p.unlink()
parts.rmdir()
print('Official PyTorch wheel SHA256 verified',flush=True)


