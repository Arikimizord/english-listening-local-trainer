"""Offline agent protocol v1. No shell interpolation, auto-download, or owner approval."""
import argparse,contextlib,ctypes,datetime,hashlib,importlib.metadata,json,os,pathlib,re,shutil,subprocess,sys,time,uuid,traceback
ROOT=pathlib.Path(__file__).resolve().parents[1];JOBS=ROOT/'jobs';VERSION='stage4-v1'
class Fault(Exception):
 def __init__(self,code,message,detail=None):self.code,self.message,self.detail=code,message,detail
class Parser(argparse.ArgumentParser):
 def error(self,message):raise Fault(2,message)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
def read(p):
 try:return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
 except (OSError,ValueError) as e:raise Fault(2,'Cannot read valid JSON',str(e))
def atomic(p,x):
 p=path_in(p,JOBS);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
 with t.open('w',encoding='utf-8',newline='\n') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def path_in(p,base=ROOT):
 raw=pathlib.Path(os.path.abspath(p))
 if raw.is_relative_to(JOBS.absolute()):
  for item in [raw,*raw.parents]:
   if item.exists() and (item.is_symlink() or getattr(item.lstat(),'st_file_attributes',0)&0x400):raise Fault(2,'Reparse links are forbidden in jobs',str(item))
   if item==JOBS:break
 p=raw.resolve()
 if not p.is_relative_to(base.resolve()):raise Fault(2,'Path escapes workspace',str(p))
 return p
def jobdir(job):
 if not re.fullmatch(r'[a-f0-9]{32}',job or ''):raise Fault(2,'Invalid job_id')
 p=path_in(JOBS/job,JOBS)
 if not (p/'job.json').is_file():raise Fault(2,'Job not found',job)
 return p
def alive(pid):
 if not isinstance(pid,int) or pid<=0:return False
 if os.name=='nt':
  k=ctypes.WinDLL('kernel32',use_last_error=True);k.OpenProcess.restype=ctypes.c_void_p;k.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];k.CloseHandle.argtypes=[ctypes.c_void_p]
  h=k.OpenProcess(0x1000,False,pid)
  if not h:return ctypes.get_last_error()==5
  code=ctypes.c_ulong();k.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
  ok=k.GetExitCodeProcess(h,ctypes.byref(code));k.CloseHandle(h);return not ok or code.value==259
 try:os.kill(pid,0);return True
 except ProcessLookupError:return False
 except PermissionError:return True
@contextlib.contextmanager
def lock_guard(p):
 import msvcrt
 gp=path_in(p.with_name(p.name+'.guard'),JOBS);f=gp.open('a+b')
 try:
  if f.tell()==0:f.write(b' ');f.flush()
  for attempt in range(40):
   try:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1);break
   except OSError:
    if attempt==39:raise Fault(4,'Lock guard busy')
    time.sleep(.025)
  try:yield
  finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
 finally:f.close()
@contextlib.contextmanager
def mutex(p):
 p=path_in(p,JOBS);p.parent.mkdir(parents=True,exist_ok=True);token=uuid.uuid4().hex
 with lock_guard(p):
  if p.exists():
   try:old=read(p)
   except Fault:raise Fault(4,'Lock unreadable; manual inspection required',str(p))
   if alive(old.get('pid')) or alive(old.get('child_pid')):raise Fault(4,'Job or GPU is busy',old)
   p.unlink()
  atomic(p,{'pid':os.getpid(),'token':token,'created_at':now()})
 try:yield token
 finally:
  with lock_guard(p):
   if p.exists() and read(p).get('token')==token:p.unlink()
def code_fingerprint():
 files=['config/models-stage3.lock.json','config/requirements-win-py311.lock','scripts/pipeline-worker.py','scripts/private-runtime.py','scripts/subtitle_formats.py','scripts/sentence_units.py','scripts/boundary_repair.py','scripts/quality_pipeline.py','scripts/workstation-core.py','scripts/environment.ps1','scripts/workstation-bootstrap.py','workstation.ps1','workstation.cmd']
 return digest({f:sha(ROOT/f) for f in files})
def models_check(full=True):
 lock=read(ROOT/'config/models-stage3.lock.json');files=[];errors=[]
 for m in lock['models']:
  for e in m['files']:
   p=path_in(ROOT/m['directory']/e['name']);good=p.is_file() and p.stat().st_size==e['size']
   if good and full:
    if e.get('sha256'):good=sha(p)==e['sha256']
    else:
     h=hashlib.sha1();h.update(f"blob {e['size']}\0".encode());h.update(p.read_bytes());good=h.hexdigest()==e['git_blob_sha1']
   files.append({'path':str(p),'ok':good})
   if not good:errors.append(str(p))
 if errors:raise Fault(3,'Pinned models missing or changed; no automatic download',errors)
 return files
def doctor(quick=False):
 files=models_check(not quick);p=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.free','--format=csv,noheader'],capture_output=True,text=True,encoding='utf-8',timeout=15)
 if p.returncode:raise Fault(3,'GPU discovery failed',p.stderr)
 expected=read(ROOT/'planning/environment-validation.json')['packages'];actual={d.metadata['Name'].lower():d.version for d in importlib.metadata.distributions()}
 changed=[x['name'] for x in expected if actual.get(x['name'].lower())!=x['version']]
 if changed:raise Fault(3,'Core dependency version mismatch',changed)
 return {'model_files':files,'full_hash_check':not quick,'gpu':p.stdout.strip(),'network':'offline; no downloads','model_inference_performed':False,'production_quality_validated':False,'warnings':(['Quick mode only checks file sizes'] if quick else [])}
def probe(audio):
 p=subprocess.run([str(ROOT/'runtime/ffmpeg/ffmpeg-7.1.1-full_build-shared/bin/ffprobe.exe'),'-v','error','-protocol_whitelist','file,pipe','-select_streams','a:0','-show_entries','format=duration:stream=codec_type','-of','json',str(audio)],capture_output=True,text=True,encoding='utf-8',timeout=30)
 try:
  info=json.loads(p.stdout);assert info.get('streams') and info['streams'][0]['codec_type']=='audio'
  d=float(info['format']['duration']);assert 0<d<86400
 except Exception:raise Fault(2,'Audio probe failed',p.stderr[-2000:])
 return d
def configuration(filename):
 filename=pathlib.Path(filename).resolve();c=read(filename)
 if not isinstance(c,dict):raise Fault(2,'Config must be an object')
 unknown=set(c)-{'schema_version','audio','language','reference_text','reference_segments','timeout_seconds'}
 if unknown:raise Fault(2,'Unknown configuration fields',sorted(unknown))
 if c.get('schema_version',1)!=1 or c.get('language','en')!='en':raise Fault(2,'Only schema 1 and English are currently supported')
 raw=c.get('audio')
 if not isinstance(raw,str) or '://' in raw or raw.startswith(('\\\\','//')):raise Fault(2,'audio must be a local file path')
 audio=pathlib.Path(raw);audio=(filename.parent/audio).resolve() if not audio.is_absolute() else audio.resolve()
 if not audio.is_file():raise Fault(2,'Audio file missing',str(audio))
 duration=probe(audio);ref=c.get('reference_text');segments=c.get('reference_segments')
 if ref is not None and segments is not None:raise Fault(2,'Choose reference_text or reference_segments')
 if ref is not None and (not isinstance(ref,str) or not ref.strip() or duration>60):raise Fault(2,'reference_text requires a nonempty string and audio <=60s; for longer audio supply timed reference_segments or edit ASR segments')
 if segments is not None:
  from subtitle_formats import normalize_and_validate
  if not isinstance(segments,list) or not segments:raise Fault(2,'reference_segments must be a nonempty list')
  try:
   normalize_and_validate({'segments':segments},duration)
   if any(x['end']-x['start']>60 or x['start']<0 or x['end']>duration for x in segments):raise ValueError('Reference segments must each be <=60 seconds and strictly within the media bounds')
  except (ValueError,TypeError,KeyError) as e:raise Fault(2,'Invalid reference segments',str(e))
 timeout=c.get('timeout_seconds',1800)
 if not isinstance(timeout,int) or isinstance(timeout,bool) or not 1<=timeout<=86400:raise Fault(2,'timeout_seconds must be 1..86400')
 models_check(False)
 normalized={'schema_version':1,'audio':str(audio),'language':'en','reference_text':ref,'reference_segments':segments,'timeout_seconds':timeout}
 return {'configuration':normalized,'audio_sha256':sha(audio),'duration_seconds':duration,'input_bytes':audio.stat().st_size,'pipeline_fingerprint':code_fingerprint(),'downloads_required':False,'warnings':['Reference text is user supplied; alignment does not establish textual correctness.'] if ref or segments else []}
def loadjob(p):
 s=read(path_in(p/'job.json',p));original=read(path_in(p/'config-snapshot.json',p))
 if s['configuration']!=original['configuration'] or s['audio_sha256']!=original['audio_sha256']:raise Fault(7,'Immutable job configuration was modified; create a new job')
 return s
def no_orphan(s):
 if alive(s.get('worker_pid')):raise Fault(4,'Worker still alive; wait before modifying this job')
def savejob(p,s):s['updated_at']=now();atomic(p/'job.json',s)
def createjob(plan):
 JOBS.mkdir(exist_ok=True);p=path_in(JOBS/uuid.uuid4().hex);p.mkdir()
 audio=pathlib.Path(plan['configuration']['audio']);dest=p/('input'+audio.suffix.lower());shutil.copyfile(audio,dest)
 if sha(dest)!=plan['audio_sha256'] or sha(audio)!=plan['audio_sha256']:raise Fault(7,'Audio changed while snapshotting')
 s={'schema_version':1,'job_id':p.name,'created_at':now(),'status':'created','owner_review':'pending','configuration':plan['configuration'],'source_audio':str(audio),'audio_snapshot':dest.name,'audio_sha256':plan['audio_sha256'],'duration_seconds':plan['duration_seconds'],'stages':{},'patches':[],'outputs':{},'warnings':plan['warnings']}
 atomic(p/'config-snapshot.json',plan);savejob(p,s);return p

def cached(p,s,name,fingerprint):
 record=s['stages'].get(name,{})
 return record.get('status')=='completed' and record.get('fingerprint')==fingerprint and all(path_in(p/f,p).is_file() and sha(p/f)==h for f,h in record.get('files',{}).items()) and bool(record.get('files'))
def execute_worker(p,s,name,args,fingerprint):
 output=path_in(p/(name+'.json'),p);log=path_in(p/(name+'.log'),p);s['status']='running';s['active_stage']=name;s['manager_pid']=os.getpid();s['stages'][name]={'status':'running','fingerprint':fingerprint};savejob(p,s)
 with mutex(JOBS/'gpu.lock') as token:
  child=None
  try:
   with log.open('a',encoding='utf-8') as stream:
    stream.write('\n--- '+now()+' ---\n');stream.flush()
    command=[sys.executable,'-I','-X','utf8',str(ROOT/'scripts/pipeline-worker.py'),'--stage',name,'--audio',str(p/s['audio_snapshot']),'--output',str(output),*args]
    child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT,env=dict(os.environ))
    lock=read(JOBS/'gpu.lock');lock['child_pid']=child.pid;atomic(JOBS/'gpu.lock',lock)
    s['worker_pid']=child.pid;savejob(p,s);started=time.monotonic()
    while child.poll() is None:
     if (p/'cancel.request').exists():raise Fault(6,'Cancellation requested')
     if time.monotonic()-started>s['configuration']['timeout_seconds']:raise Fault(5,'Worker timeout')
     time.sleep(0.2)
    if child.returncode:raise Fault(5,'Worker failed',{'stage':name,'exit_code':child.returncode,'log':str(log)})
    if (p/'cancel.request').exists():raise Fault(6,'Cancellation requested')
    result=read(output)
    if result.get('stage')!=name or result.get('device')!='cuda' or result.get('audio_sha256')!=s['audio_sha256'] or abs(result.get('duration_seconds',-1)-s['duration_seconds'])>0.05:raise Fault(5,'Worker returned invalid provenance')
    s['stages'][name]={'status':'completed','fingerprint':fingerprint,'files':{output.name:sha(output)},'completed_at':now()};savejob(p,s)
  finally:
   if child is not None and child.poll() is None:
    child.terminate()
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
   s.pop('worker_pid',None);savejob(p,s)
def alignment_input(p,s):
 asr=read(p/'asr.json');c=s['configuration']
 segments=c['reference_segments'] or ([{'start':0.0,'end':s['duration_seconds'],'text':c['reference_text']}] if c['reference_text'] else asr['segments'])
 segments=[{'start':x['start'],'end':x['end'],'text':x['text']} for x in segments]
 for patch_name in s['patches']:
  patch=read(path_in(p/patch_name,p))
  if patch['base_transcript_sha256']!=sha(p/'asr.json'):raise Fault(7,'Patch base changed; manual rebase required',patch_name)
  if c['reference_segments'] or c['reference_text']:raise Fault(7,'ASR segment patches cannot be mixed with configured reference text')
  for key,value in patch['segment_text'].items():segments[int(key)]['text']=value
 data={'schema_version':1,'segments':segments};atomic(p/'alignment-input.json',data);return data

def export_job(p,s):
 no_orphan(s)
 if sha(path_in(p/s['audio_snapshot'],p))!=s['audio_sha256']:raise Fault(7,'Audio snapshot hash mismatch')
 pipeline=code_fingerprint();asr_fp=digest({'audio':s['audio_sha256'],'pipeline':pipeline,'language':'en'})
 if not cached(p,s,'asr',asr_fp):raise Fault(7,'ASR provenance is stale; resume the job')
 effective=alignment_input(p,s);expected=digest({'asr':sha(p/'asr.json'),'input':effective,'pipeline':pipeline})
 if not cached(p,s,'align',expected):raise Fault(7,'Alignment provenance is stale; resume alignment')
 from subtitle_formats import normalize_and_validate,render_srt,render_ass
 if 'align' not in s['stages'] or s['stages']['align'].get('status')!='completed' or sha(p/'align.json')!=s['stages']['align']['files']['align.json']:raise Fault(7,'Current alignment not ready; run/resume alignment first')
 if s['stages']['align'].get('input_sha')!=sha(p/'alignment-input.json'):raise Fault(7,'Alignment input has changed')
 fp=digest({'alignment':sha(p/'align.json'),'formatter':sha(ROOT/'scripts/subtitle_formats.py'),'sentences':sha(ROOT/'scripts/sentence_units.py')})
 if cached(p,s,'export',fp):return s['outputs']
 from sentence_units import regroup
 normalized=normalize_and_validate(read(p/'align.json'),s['duration_seconds'])
 try:normalized=regroup(normalized)
 except ValueError as e:
  normalized['sentence_policy']='unresolved';normalized['warnings'].append({'code':'sentence_regroup_requires_review','detail':str(e)})
 normalized['audio_sha256']=s['audio_sha256'];folder=path_in(p/'exports'/uuid.uuid4().hex,p);folder.mkdir(parents=True)
 atomic(folder/'subtitles.json',normalized)
 for name,text in [('subtitles.srt',render_srt(normalized)),('subtitles.ass',render_ass(normalized))]:
  (folder/name).write_text(text,encoding='utf-8',newline='\n')
 files={str(x.relative_to(p)):sha(x) for x in folder.iterdir() if x.is_file()};atomic(folder/'manifest.json',{'schema_version':1,'files':files,'fingerprint':fp,'audio_sha256':s['audio_sha256'],'review_status':'pending'})
 files[str((folder/'manifest.json').relative_to(p))]=sha(folder/'manifest.json')
 s['stages']['export']={'status':'completed','fingerprint':fp,'files':files};s['outputs']={x.name:str(x) for x in folder.iterdir()};s['warnings']=list({json.dumps(w,ensure_ascii=False,sort_keys=True):w for w in s.get('warnings',[])+normalized.get('warnings',[])}.values());savejob(p,s);return s['outputs']
def run_job(p,stage):
 with mutex(p/'run.lock'):
  s=loadjob(p)
  if sha(path_in(p/s['audio_snapshot'],p))!=s['audio_sha256']:raise Fault(7,'Audio snapshot hash mismatch')
  no_orphan(s)
  (p/'cancel.request').unlink(missing_ok=True);s['owner_review']='pending';pipeline=code_fingerprint()
  try:
   models_check();asr_fp=digest({'audio':s['audio_sha256'],'pipeline':pipeline,'language':'en'})
   if not cached(p,s,'asr',asr_fp):
    s['outputs']={}
    for downstream in ['align','export']:
     if downstream in s['stages']:s['stages'][downstream]['status']='invalidated'
    savejob(p,s);execute_worker(p,s,'asr',[],asr_fp)
   if stage!='asr':
    data=alignment_input(p,s);align_fp=digest({'asr':sha(p/'asr.json'),'input':data,'pipeline':pipeline})
    if not cached(p,s,'align',align_fp):
     s['outputs']={}
     if 'export' in s['stages']:s['stages']['export']['status']='invalidated'
     savejob(p,s);execute_worker(p,s,'align',['--segments',str(p/'alignment-input.json')],align_fp)
    s['stages']['align']['input_sha']=sha(p/'alignment-input.json');savejob(p,s)
    if stage in ['all','export']:export_job(p,s)
   s['status']='completed';s['active_stage']=None;s.pop('error',None);savejob(p,s);return s
  except (Exception,KeyboardInterrupt) as e:
   f=e if isinstance(e,Fault) else Fault(6 if isinstance(e,KeyboardInterrupt) else 5,str(e));s['status']='canceled' if f.code==6 else 'failed';s['error']={'code':f.code,'message':f.message,'detail':f.detail};f.job_id=p.name;s['owner_review']='pending';savejob(p,s);raise f

def status(p):
 s=loadjob(p)
 if s['status']=='running' and not alive(s.get('manager_pid')):s['observed_status']='worker_orphaned' if alive(s.get('worker_pid')) else 'interrupted'
 return s

def review(p,apply=None):
 with mutex(p/'run.lock'):
  s=loadjob(p);no_orphan(s)
  if not (p/'asr.json').is_file():raise Fault(7,'ASR output required before review')
  asr=read(p/'asr.json');base=sha(p/'asr.json')
  if apply:
   patch=read(pathlib.Path(apply).resolve())
   if not isinstance(patch,dict) or set(patch)-{'schema_version','base_transcript_sha256','segment_text'} or patch.get('schema_version')!=1:raise Fault(2,'Invalid patch schema')
   if patch.get('base_transcript_sha256')!=base:raise Fault(7,'Patch base does not match current ASR')
   edits=patch.get('segment_text')
   if not isinstance(edits,dict) or not edits:raise Fault(2,'segment_text must be a nonempty object')
   if s['configuration']['reference_text'] or s['configuration']['reference_segments']:raise Fault(7,'Patch ASR segments only when no reference text is configured')
   for k,v in edits.items():
    if not isinstance(k,str) or not re.fullmatch(r'0|[1-9][0-9]*',k) or int(k)>=len(asr['segments']) or not isinstance(v,str) or not v.strip():raise Fault(2,'Invalid segment edit',k)
   dest=path_in(p/'patches'/(uuid.uuid4().hex+'.json'),p);atomic(dest,patch);s['patches'].append(str(dest.relative_to(p)))
   for name in ['align','export']:
    if name in s['stages']:s['stages'][name]['status']='invalidated'
   s['status']='needs_realign';s['outputs']={};s['owner_review']='pending';savejob(p,s)
   return {'job_id':p.name,'patch':str(dest),'next_action':'run --job '+p.name+' --resume','review_status':'pending'}
  dest=path_in(p/'reviews'/uuid.uuid4().hex,p);dest.mkdir(parents=True)
  template={'schema_version':1,'base_transcript_sha256':base,'segment_text':{str(i):x['text'] for i,x in enumerate(asr['segments'])}}
  atomic(dest/'text-patch.json',template)
  data={'schema_version':1,'job_id':p.name,'asr_sha256':base,'patch_template':str(dest/'text-patch.json'),'asr':str(p/'asr.json'),'alignment':str(p/'align.json') if (p/'align.json').exists() else None,'applied_patches':s['patches'],'review_status':'pending','note':'JSON file review only. Waveform GUI and playback are stage 5; text edits require re-alignment.'}
  atomic(dest/'review.json',data);return data

def main():
 args0=[x for x in sys.argv[1:] if x not in ['--json','--offline']]
 parser=Parser(description='Local offline subtitle workstation; JSON protocol v1');subs=parser.add_subparsers(dest='command',required=True)
 sub=subs.add_parser('doctor');sub.add_argument('--quick',action='store_true')
 sub=subs.add_parser('plan');sub.add_argument('--config',required=True)
 sub=subs.add_parser('run');group=sub.add_mutually_exclusive_group(required=True);group.add_argument('--config');group.add_argument('--job');sub.add_argument('--resume',action='store_true');sub.add_argument('--stage',choices=['asr','align','export','all'],default='all')
 for name in ['status','cancel','export','review']:
  sub=subs.add_parser(name);sub.add_argument('--job',required=True)
  if name=='review':sub.add_argument('--apply')
 a=parser.parse_args(args0);globals()['COMMAND']=a.command
 if a.command=='doctor':return doctor(a.quick)
 if a.command=='plan':return configuration(a.config)
 if a.command=='run':
  if a.job and not a.resume:raise Fault(2,'Existing jobs require --resume')
  if a.config and a.resume:raise Fault(2,'--resume requires --job')
  p=jobdir(a.job) if a.job else createjob(configuration(a.config));return run_job(p,a.stage)
 p=jobdir(a.job)
 if a.command=='status':return status(p)
 if a.command=='cancel':
  s=loadjob(p)
  if s['status']!='running':return {'job_id':p.name,'status':s['status'],'cancel_requested':False}
  atomic(p/'cancel.request',{'requested_at':now()});return {'job_id':p.name,'cancel_requested':True,'note':'Requests manager-owned child termination; never kills arbitrary PIDs.'}
 if a.command=='review':return review(p,a.apply)
 if a.command=='export':
  with mutex(p/'run.lock'):
   s=loadjob(p);return {'job_id':p.name,'outputs':export_job(p,s),'review_status':'pending'}
if __name__=='__main__':
 started=time.monotonic();code=0
 try:payload=main();result={'schema_version':1,'ok':True,'review_status':'pending','outputs':{},'warnings':[],'errors':[],**payload}
 except Fault as e:code=e.code;result={'job_id':getattr(e,'job_id',None),'schema_version':1,'ok':False,'review_status':'pending','outputs':{},'warnings':[],'errors':[{'code':e.code,'message':e.message,'detail':e.detail}]}
 except Exception as e:code=5;result={'schema_version':1,'ok':False,'review_status':'pending','outputs':{},'warnings':[],'errors':[{'code':5,'message':str(e),'detail':traceback.format_exc()}]}
 result['command']=globals().get('COMMAND');result['stage']=result.get('active_stage');result['elapsed_seconds']=round(time.monotonic()-started,3);print(json.dumps(result,ensure_ascii=False,allow_nan=False));sys.exit(code)
