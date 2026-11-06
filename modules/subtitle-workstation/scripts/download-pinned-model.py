"""Download a pinned large model file via HTTPS ranges; never bypass upstream SHA256."""
import pathlib,urllib.request,hashlib,concurrent.futures,time,os,json

def download_pinned(root,dest,entry,workers=16):
    root=pathlib.Path(root).resolve();dest=pathlib.Path(dest)
    total=entry['size'];expected=entry['sha256'];assert expected and len(expected)==64
    if dest.exists() and dest.stat().st_size==total and hashlib.file_digest(dest.open('rb'),'sha256').hexdigest()==expected:return
    parts=root/'cache/downloads/model-parts'/expected;parts.mkdir(parents=True,exist_ok=True)
    assert parts.resolve().is_relative_to(root)
    chunk=8*1024**2
    jobs=[(i,s,min(s+chunk,total)-1) for i,s in enumerate(range(0,total,chunk))]
    def get(job):
        i,start,end=job;p=parts/f'{i:05d}.part';length=end-start+1
        for attempt in range(8):
            done=p.stat().st_size if p.exists() else 0
            if done==length:return length
            if done>length:raise RuntimeError('Oversized download part')
            offset=start+done;sep='&' if '?' in entry['url'] else '?'
            url=entry['url']+sep+f'download=true&workbench-range={offset}-{end}&retry={attempt}'
            try:
                req=urllib.request.Request(url,headers={'Range':f'bytes={offset}-{end}','Accept-Encoding':'identity','User-Agent':'subtitle-workbench-stage3'})
                with urllib.request.urlopen(req,timeout=90) as r:
                    if r.status!=206 or r.headers.get('Content-Range')!=f'bytes {offset}-{end}/{total}':raise RuntimeError('Server returned wrong byte range')
                    with p.open('ab') as out:
                        while data:=r.read(256*1024):out.write(data);out.flush()
                if p.stat().st_size!=length:raise RuntimeError('Short response; retaining partial bytes')
                return length
            except Exception as e:
                print(f"{dest.name} part {i} retry {attempt+1}: {type(e).__name__}: {str(e)[:140]}",flush=True)
                if attempt==7:raise
                time.sleep(min(attempt+1,5))
    print(f'Ranged model download: {dest.name}, {total} bytes, {workers} connections',flush=True)
    completed=0;last=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for f in concurrent.futures.as_completed([pool.submit(get,j) for j in jobs]):
            completed+=f.result()
            if time.monotonic()-last>20 or completed==total:
                print(f'{dest.name}: {completed/total:.1%}',flush=True);last=time.monotonic()
    temp=dest.with_name(dest.name+'.verified-download');dest.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256()
    with temp.open('wb') as out:
        for i,_,_ in jobs:
            with (parts/f'{i:05d}.part').open('rb') as src:
                while data:=src.read(4*1024**2):out.write(data);h.update(data)
    assert temp.stat().st_size==total and h.hexdigest()==expected,'Upstream LFS SHA256 mismatch'
    os.replace(temp,dest)
    for i,_,_ in jobs:(parts/f'{i:05d}.part').unlink()
    parts.rmdir()
    print(f'Upstream LFS SHA256 verified: {dest.name}',flush=True)
