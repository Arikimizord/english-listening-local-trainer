"""Local review server. Run with private Python -I -X utf8, --job JOB_ID."""
import argparse, copy, hashlib, json, pathlib, re, secrets, sys, uuid, importlib.util, subprocess, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from subtitle_formats import normalize_and_validate, render_srt, render_ass

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def validate(data, base):
 if not isinstance(data,dict) or data.get('base_sha256')!=base:raise ValueError('Baseline changed; reopen review')
 raw=data['document']; dur=raw['duration_ms']
 converted={'segments':[{'start':s['start_ms']/1000,'end':s['end_ms']/1000,'text':s['text'],'words':[{'word':w['word'],'start':None if w['start_ms'] is None else w['start_ms']/1000,'end':None if w['end_ms'] is None else w['end_ms']/1000} for w in s.get('words',[])]} for s in raw['segments']]}
 result=normalize_and_validate(converted,dur/1000)
 result['audio_sha256']=raw.get('audio_sha256')
 for key in ('sentence_policy','sentence_report','boundary_repair','quality_evidence'):
  if key in raw:result[key]=raw[key]
 for src,dst in zip(raw['segments'],result['segments']):
  for old,w in zip(src.get('words',[]),dst['words']):
   w['timing_method']=old.get('timing_method','manual_review_candidate')
  if 'alignment_evidence' in src:dst['alignment_evidence']=src['alignment_evidence']
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--job',required=True);ap.add_argument('--port',type=int,default=0);a=ap.parse_args()
 if not re.fullmatch('[a-f0-9]{32}',a.job):raise ValueError('Invalid job ID')
 job=ROOT/'jobs'/a.job;s=read(job/'job.json');audio=(job/s['audio_snapshot']).resolve();source=pathlib.Path(s['outputs']['subtitles.json']).resolve()
 for p in (job.resolve(),audio,source):
  if not p.is_relative_to((ROOT/'jobs').resolve()):raise ValueError('Unsafe path')
 if sha(audio)!=s['audio_sha256']:raise ValueError('Audio hash mismatch')
 manifest=read(source.parent/'manifest.json')
 if manifest['files'].get(str(source.relative_to(job)))!=sha(source):raise ValueError('Subtitle hash mismatch')
 base=sha(source);original=read(source);token=secrets.token_urlsafe(24)
 spec=importlib.util.spec_from_file_location('review_core',ROOT/'scripts/workstation-core.py')
 core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
 def check_source():
  if sha(source)!=base or sha(audio)!=s['audio_sha256']:raise ValueError('Source changed; reopen task')
 def revision(name):
  if not re.fullmatch('[a-f0-9]{32}',name):raise ValueError('Invalid revision')
  folder=core.path_in(job/'reviews'/name,job)
  m=read(folder/'manifest.json')
  if m['base_sha256']!=base or m['audio_sha256']!=s['audio_sha256']:raise ValueError('Revision baseline conflict')
  for name,h in m['files'].items():
   if sha(core.path_in(folder/name,folder))!=h:raise ValueError('Revision file hash mismatch')
  return folder
 def versions():
  result=[]
  for f in sorted((job/'reviews').glob('*'),key=lambda f:f.stat().st_mtime,reverse=True):
   if re.fullmatch('[a-f0-9]{32}',f.name):
    try:revision(f.name);result.append({'id':f.name,'created_at':read(f/'manifest.json').get('created_at',f.name)})
    except Exception:pass
  return result
 def response_document(doc,rev=None):return {'document':doc,'base_sha256':base,'job':a.job,'revision':rev,'versions':versions(),'review_status':'pending'}
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def send(self,body,ctype='application/json',code=200):
   self.send_response(code);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
  def do_GET(self):
   if self.path=='/'+token+'/':return self.send((ROOT/'scripts/review.html').read_bytes(),'text/html; charset=utf-8')
   if self.path=='/'+token+'/data':
    check_source();v=versions();rev=v[0]['id'] if v else None
    return self.send(json.dumps(response_document(read(revision(rev)/'subtitles.json') if rev else original,rev)).encode())
   if self.path.startswith('/'+token+'/revision/'):
    check_source();rev=self.path.rsplit('/',1)[-1]
    return self.send(json.dumps(response_document(read(revision(rev)/'subtitles.json'),rev)).encode())
   if self.path.startswith('/'+token+'/download/'):
    _,rev,name=self.path[len('/'+token+'/download'):].split('/')
    if name not in ('subtitles.json','subtitles.srt','subtitles.ass','manifest.json'):return self.send(b'{}',code=404)
    return self.send((revision(rev)/name).read_bytes(),'application/octet-stream')
   if self.path=='/'+token+'/audio':
    size=audio.stat().st_size;start=0;end=size-1;code=200
    with audio.open('rb') as f:header=f.read(16)
    mime='audio/mp4' if header[4:8]==b'ftyp' else 'audio/flac' if header[:4]==b'fLaC' else 'audio/wav' if header[:4]==b'RIFF' else 'audio/mpeg'
    requested=self.headers.get('Range')
    if requested:
     match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
     if not match or not any(match.groups()):return self.send(b'Invalid range',code=416)
     lo,hi=match.groups()
     if lo:start=int(lo);end=min(int(hi),end) if hi else end
     else:start=max(0,size-int(hi))
     if start>end or start>=size:return self.send(b'Invalid range',code=416)
     code=206
    self.send_response(code);self.send_header('Content-Type',mime);self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
    if code==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
    self.end_headers()
    with audio.open('rb') as f:
     f.seek(start);left=end-start+1
     while left:
      block=f.read(min(left,65536))
      if not block:break
      self.wfile.write(block);left-=len(block)
    return
   self.send(b'{}',code=404)
  def do_POST(self):
   try:
    if self.path not in ('/'+token+'/save','/'+token+'/align','/'+token+'/sentences'):return self.send(b'{}',code=404)
    if self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}'):raise ValueError('Invalid origin')
    size=int(self.headers.get('Content-Length',0))
    if not 0<size<8_000_000:raise ValueError('Request size invalid')
    data=json.loads(self.rfile.read(size))
    if sha(source)!=base or sha(audio)!=s['audio_sha256']:raise ValueError('Source changed')
    if data['document']['duration_ms']!=original['duration_ms']:raise ValueError('Duration changed')
    doc=validate(data,base)
    doc['audio_sha256']=s['audio_sha256']
    if self.path.endswith('/sentences'):
     from sentence_units import regroup
     from quality_pipeline import repair_document
     return self.send(json.dumps(response_document(regroup(repair_document(job,doc,core)))).encode())
    if self.path.endswith('/align'):
     idx=data.get('segment_index')
     if type(idx) is not int or not 0<=idx<len(doc['segments']):raise ValueError('Invalid segment index')
     segment=doc['segments'][idx]
     if segment['end_ms']-segment['start_ms']>60000:raise ValueError('Local alignment window exceeds 60 seconds')
     with core.mutex(job/'run.lock'),core.mutex(ROOT/'jobs/gpu.lock') as lock_token:
      core.no_orphan(core.loadjob(job));check_source()
      work=core.path_in(job/'review-work'/uuid.uuid4().hex,job);work.mkdir(parents=True)
      inp=work/'input.json';out=work/'aligned.json'
      core.atomic(inp,{'segments':[{'start':segment['start_ms']/1000,'end':segment['end_ms']/1000,'text':segment['text']}]})
      args=[sys.executable,'-I','-B','-X','utf8',str(ROOT/'scripts/pipeline-worker.py'),'--stage','align','--audio',str(audio),'--segments',str(inp),'--output',str(out)]
      with (work/'worker.log').open('w',encoding='utf-8') as log:
       child=subprocess.Popen(args,stdout=log,stderr=log)
       lock=core.read(ROOT/'jobs/gpu.lock');lock['child_pid']=child.pid;core.atomic(ROOT/'jobs/gpu.lock',lock)
       try:code=child.wait(timeout=600)
       except subprocess.TimeoutExpired:child.kill();child.wait();raise ValueError('Local alignment timed out')
      if code:raise ValueError('Local alignment failed; see '+str(work/'worker.log'))
      aligned=read(out)
      if aligned['device']!='cuda' or aligned['audio_sha256']!=s['audio_sha256']:raise ValueError('Invalid alignment provenance')
      part=normalize_and_validate(aligned,s['duration_seconds'])['segments']
      # Preserve the edited sentence boundaries, merging only its aligned words.
      words=[w for row in part for w in row['words']]
      if any(w[k] is not None and not segment['start_ms']<=w[k]<=segment['end_ms'] for w in words for k in ('start_ms','end_ms')):raise ValueError('Aligned words escaped selected sentence')
      segment['words']=words
      segment['alignment_evidence']=str(out.relative_to(job))
      check_source()
     return self.send(json.dumps(response_document(doc)).encode())
    dest=core.path_in(job/'reviews'/uuid.uuid4().hex,job);dest.mkdir(parents=True)
    (dest/'patch.json').write_text(json.dumps({'schema_version':1,'base_sha256':base,'base_path':str(source),'document':doc,'review_status':'pending'},ensure_ascii=False,indent=2),encoding='utf-8')
    (dest/'subtitles.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
    (dest/'subtitles.srt').write_text(render_srt(doc),encoding='utf-8')
    (dest/'subtitles.ass').write_text(render_ass(doc),encoding='utf-8')
    (dest/'manifest.json').write_text(json.dumps({'base_sha256':base,'audio_sha256':s['audio_sha256'],'review_status':'pending','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'parent_revision':data.get('revision'),'files':{p.name:sha(p) for p in dest.iterdir()}},indent=2),encoding='utf-8')
    self.send(json.dumps({'saved':str(dest),'revision':dest.name,'versions':versions(),'review_status':'pending'}).encode())
   except Exception as e:self.send(json.dumps({'error':str(e)}).encode(),code=400)
 server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler)
 print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/{token}/','review_status':'pending'}),flush=True);server.serve_forever()
if __name__=='__main__':main()
