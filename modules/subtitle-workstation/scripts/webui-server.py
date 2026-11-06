"""Loopback-only UI for the existing isolated offline workstation CLI. Stdlib only."""
from __future__ import annotations
import argparse, datetime, hashlib, json, mimetypes, os, pathlib, re, secrets
import subprocess, sys, threading, time, urllib.parse, webbrowser, zipfile, importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT=pathlib.Path(__file__).resolve().parents[1]
PYTHON=ROOT/'envs/subtitle/Scripts/python.exe'
MAX_AUDIO=2*1024**3
JID=re.compile(r'^[a-f0-9]{32}$')
STAGES={'asr':'语音识别与重复校验','align':'词级时间对齐','export':'整理字幕文件'}
_spec=importlib.util.spec_from_file_location('webui_core',ROOT/'scripts/workstation-core.py')
CORE=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(CORE)
class Canceled(Exception):pass

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def within(path,base):
    p=path.resolve();base=base.resolve()
    if not p.is_relative_to(base):raise ValueError('文件路径越界')
    return p
def job_path(jid):
    if not isinstance(jid,str) or not JID.fullmatch(jid):raise ValueError('无效的任务编号')
    p=within(ROOT/'jobs'/jid,ROOT/'jobs')
    if not (p/'job.json').is_file():raise ValueError('找不到任务')
    return p
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temp,path)
def cli_args(*args):
    return ['powershell.exe','-NoProfile','-File',str(ROOT/'scripts/webui-cli.ps1'),*args,'--json']
def run_cli(*args):
    result=subprocess.run(cli_args(*args),stdin=subprocess.DEVNULL,capture_output=True,
                          encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW)
    try:data=json.loads(result.stdout.lstrip('\ufeff'))
    except ValueError:raise ValueError('工作台未返回有效结果：'+(result.stderr or result.stdout)[-1500:])
    if result.returncode or not data.get('ok'):
        if any(x.get('code')==6 for x in data.get('errors',[])):raise Canceled('任务已取消，可稍后恢复')
        raise ValueError('；'.join(str(x.get('message',x)) for x in data.get('errors',[])) or '工作台处理失败')
    return data

def artifacts(jid):
    job=job_path(jid);state=read(job/'job.json');audio=within(job/state['audio_snapshot'],job)
    if sha(audio)!=state['audio_sha256']:raise ValueError('音频快照校验失败')
    candidates=sorted((job/'reviews').glob('*/subtitles.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    output=state.get('outputs',{}).get('subtitles.json')
    if output:candidates.append(within(pathlib.Path(output),job))
    for source in candidates:
        try:
            folder=within(source.parent,job);manifest=read(folder/'manifest.json')
            if manifest.get('audio_sha256')!=state['audio_sha256']:continue
            for name,digest in manifest['files'].items():
                p=within(job/name,job) if name.startswith(('exports\\','exports/')) else within(folder/name,folder)
                if not p.is_file() or sha(p)!=digest:raise ValueError('字幕校验失败')
            if not all((folder/name).is_file() for name in ('subtitles.json','subtitles.srt')):continue
            return state,audio,folder
        except (OSError,ValueError,KeyError):continue
    raise ValueError('尚无可导出的完整字幕，请先完成生成')

class Workbench:
    def __init__(self):
        self.lock=threading.RLock();self.operation=None;self.selected=None;self.reviews={};self.environment=None
        self.storage=ROOT/'ui';self.storage.mkdir(exist_ok=True)
    def jobs(self):
        result=[]
        for p in (ROOT/'jobs').glob('*/job.json'):
            if not JID.fullmatch(p.parent.name):continue
            try:
                s=read(p);status=s.get('status','unknown')
                if status=='running' and not CORE.alive(s.get('manager_pid')):
                    status='worker_orphaned' if CORE.alive(s.get('worker_pid')) else 'interrupted'
                result.append({'id':p.parent.name,'name':pathlib.Path(s['source_audio']).name,
                               'status':status,'stage':s.get('active_stage'),
                               'duration':s.get('duration_seconds',0),'created':s.get('created_at',''),
                               'has_output':bool(s.get('outputs')),'error':s.get('error')})
            except (OSError,ValueError,KeyError):continue
        return sorted(result,key=lambda j:j['created'],reverse=True)
    def snapshot(self):
        with self.lock:
            if self.operation and self.operation['status']=='running' and self.operation.get('job'):
                try:
                    s=read(job_path(self.operation['job'])/'job.json')
                    self.operation['stage']=STAGES.get(s.get('active_stage'),self.operation['stage'])
                except (OSError,ValueError):pass
            op=dict(self.operation) if self.operation else None
            return {'jobs':self.jobs(),'operation':op,'selected':self.selected,'environment':self.environment}
    def begin(self,kind,func):
        with self.lock:
            if self.operation and self.operation['status']=='running':raise ValueError('已有任务正在处理，请等待或取消')
            op={'id':secrets.token_hex(16),'kind':kind,'status':'running','stage':'准备处理','job':None,'started':time.time()}
            self.operation=op
        def work():
            try:
                result=func(op)
                with self.lock:op.update(status='completed',stage='已完成',result=result)
            except Canceled as exc:
                with self.lock:op.update(status='canceled',stage='已取消',error=str(exc))
            except Exception as exc:
                with self.lock:op.update(status='failed',stage='处理未完成',error=str(exc))
            finally:
                write(self.storage/'operations'/(op['id']+'.json'),op)
        threading.Thread(target=work,daemon=True).start();return op['id']
    def generate(self,data):
        path=data.get('path');uploaded=data.get('upload')
        if uploaded:
            if not JID.fullmatch(uploaded):raise ValueError('无效的音频导入编号')
            meta=read(self.storage/'imports'/uploaded/'source.json');path=meta['path']
            path=str(within(pathlib.Path(path),self.storage/'imports'/uploaded))
        if not isinstance(path,str) or not pathlib.Path(path).is_absolute():raise ValueError('请选择音频，或填写本机绝对路径')
        if path.startswith(('\\\\','//')) or '://' in path:raise ValueError('仅支持本机磁盘上的音频')
        source=pathlib.Path(path).resolve(strict=True)
        if not source.is_file():raise ValueError('找不到音频文件')
        def task(op):
            folder=self.storage/'operations'/op['id'];folder.mkdir(parents=True,exist_ok=True)
            config=folder/'config.json';write(config,{'schema_version':1,'audio':str(source),'language':'en','timeout_seconds':7200})
            op['stage']='检查音频与环境';run_cli('plan','--config',str(config))
            known={j['id'] for j in self.jobs()};op['stage']='准备生成'
            with (folder/'result.json').open('w',encoding='utf-8') as out,(folder/'stderr.log').open('w',encoding='utf-8') as err:
                child=subprocess.Popen(cli_args('run','--config',str(config)),stdin=subprocess.DEVNULL,
                                       stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    while child.poll() is None:
                        if not op['job']:
                            for j in self.jobs():
                                if j['id'] in known:continue
                                s=read(job_path(j['id'])/'job.json')
                                if s['configuration']['audio']==str(source):op['job']=j['id'];self.selected=j['id'];break
                        if op['job']:
                            s=read(job_path(op['job'])/'job.json');op['stage']=STAGES.get(s.get('active_stage'),'准备字幕成品')
                        time.sleep(.5)
                    code=child.returncode
                finally:
                    # Do not terminate the manager here: it owns GPU workers and cancellation.
                    # A closed browser does not cancel a job.
                    pass
            result=read(folder/'result.json')
            if not op['job'] and result.get('job_id'):op['job']=result['job_id'];self.selected=op['job']
            if code or not result.get('ok'):
                if code==6:raise Canceled('任务已取消，可在当前任务恢复')
                raise ValueError('；'.join(str(x.get('message',x)) for x in result.get('errors',[])) or '生成失败，请查看任务日志')
            # Imported bytes are staging only. Remove only after a complete,
            # hash-verified job snapshot exists; retain configuration and receipt.
            if uploaded and op['job']:
                s=read(job_path(op['job'])/'job.json');snapshot=job_path(op['job'])/s['audio_snapshot']
                if source.is_file() and sha(source)==s['audio_sha256']==sha(snapshot):source.unlink()
            return {'job_id':op['job']}
        return self.begin('generate',task)
    def resume(self,jid):
        p=job_path(jid);s=read(p/'job.json')
        if s['status']=='running' and (CORE.alive(s.get('manager_pid')) or CORE.alive(s.get('worker_pid'))):raise ValueError('此任务仍在运行，不能重复启动')
        if s['status']=='completed':raise ValueError('已完成的任务可直接试听或下载，无需重新生成')
        def task(op):
            op['job']=jid;self.selected=jid;op['stage']='恢复任务'
            return run_cli('run','--job',jid,'--resume')
        return self.begin('resume',task)
    def review(self,jid):
        job_path(jid)
        with self.lock:
            prior=self.reviews.get(jid)
            if prior and prior['process'].poll() is None:return prior['url']
            process=subprocess.Popen(['powershell.exe','-NoProfile','-File',str(ROOT/'scripts/start-review.ps1'),'-Job',jid],
                                     stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                     text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
            answer={}
            def first_line():
                try:answer['line']=process.stdout.readline()
                except Exception as e:answer['error']=str(e)
            t=threading.Thread(target=first_line,daemon=True);t.start();t.join(20)
            if t.is_alive():process.terminate();raise ValueError('修订界面启动超时')
            try:
                url=json.loads(answer.get('line',''))['url']
                if not url.startswith('http://127.0.0.1:'):raise ValueError('Unsafe review URL')
            except Exception:
                if process.poll() is None:process.terminate()
                raise ValueError('修订界面未能打开，请先完成字幕生成')
            self.reviews[jid]={'process':process,'url':url};return url
    def package(self,jid):
        state,audio,folder=artifacts(jid)
        stem=pathlib.Path(state['source_audio']).stem
        stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',stem)[:150].rstrip(' .') or '听力素材'
        key=sha(folder/'subtitles.json')[:24]+'-'+state['audio_sha256'][:12]
        dest=self.storage/'packages'/(key+'.zip');dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            temp=dest.with_name(dest.name+'.'+secrets.token_hex(5)+'.tmp')
            items={stem+audio.suffix:audio,stem+'.json':folder/'subtitles.json',stem+'.srt':folder/'subtitles.srt'}
            with zipfile.ZipFile(temp,'w') as z:
                for name,path in items.items():z.write(path,name,compress_type=zipfile.ZIP_STORED)
                z.writestr('文件清单.json',json.dumps({'schema_version':1,'audio_sha256':state['audio_sha256'],
                            'files':{name:sha(path) for name,path in items.items()}},ensure_ascii=False,indent=2))
            os.replace(temp,dest)
        return dest,stem+'-课堂素材.zip'

def make_handler(workbench,token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def route(self):
            if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':raise ValueError('无效的本机地址')
            parsed=urllib.parse.urlsplit(self.path)
            if not parsed.path.startswith('/'+token+'/'):raise ValueError('页面会话无效，请重新打开启动网址')
            return parsed.path[len(token)+2:],urllib.parse.parse_qs(parsed.query)
        def send(self,data,code=200,kind='application/json; charset=utf-8'):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode('utf-8')
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            try:
                path,q=self.route()
                if path=='':return self.send((ROOT/'scripts/webui.html').read_bytes(),kind='text/html; charset=utf-8')
                if path=='api/state':return self.send(workbench.snapshot())
                if path=='api/download':
                    file,name=workbench.package(q.get('job',[''])[0])
                    self.send_response(200);self.send_header('Content-Type','application/zip')
                    self.send_header('Content-Length',str(file.stat().st_size));self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(name));self.send_header('Cache-Control','no-store');self.end_headers()
                    with file.open('rb') as f:
                        while block:=f.read(1024*1024):self.wfile.write(block)
                    return
                if path=='api/log':
                    jid=q.get('job',[''])[0];p=job_path(jid);logs=[]
                    for name in ('asr.log','align.log'):
                        file=p/name
                        if file.is_file():
                            with file.open('rb') as f:f.seek(max(0,file.stat().st_size-10000));logs.append(name+'\n'+f.read().decode('utf-8',errors='replace'))
                    return self.send({'text':'\n\n'.join(logs) or '暂无运行日志'})
                self.send({'error':'找不到页面'},404)
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception as e:self.send({'error':str(e)},400)
        def do_POST(self):
            try:
                path,q=self.route()
                if self.headers.get('Origin')!=f'http://127.0.0.1:{self.server.server_port}':raise ValueError('请求来源无效')
                size=int(self.headers.get('Content-Length','0'))
                if path=='api/import':
                    if not 0<size<=MAX_AUDIO:raise ValueError('请选择非空且小于2GB的音频')
                    name=q.get('name',[''])[0]
                    if not name or pathlib.Path(name).name!=name or any(c in name for c in '/\\<>:"|?*\x00'):raise ValueError('音频文件名不合法')
                    if pathlib.Path(name).suffix.lower() not in ('.mp3','.m4a','.wav','.aac'):raise ValueError('请选择 MP3、M4A、WAV 或 AAC 音频')
                    ident=secrets.token_hex(16);folder=workbench.storage/'imports'/ident;folder.mkdir(parents=True)
                    file=within(folder/name,folder);remaining=size
                    try:
                        with file.open('xb') as f:
                            while remaining:
                                block=self.rfile.read(min(1024*1024,remaining))
                                if not block:raise ValueError('音频传输未完成')
                                f.write(block);remaining-=len(block)
                        write(folder/'source.json',{'path':str(file),'name':name,'bytes':size})
                    except Exception:
                        file.unlink(missing_ok=True);raise
                    return self.send({'upload':ident,'name':name,'bytes':size})
                if not 0<size<=32768:raise ValueError('请求大小无效')
                data=json.loads(self.rfile.read(size))
                if path=='api/generate':return self.send({'operation':workbench.generate(data)})
                if path=='api/resume':return self.send({'operation':workbench.resume(data.get('job'))})
                if path=='api/review':return self.send({'url':workbench.review(data.get('job'))})
                if path=='api/cancel':
                    job_path(data.get('job'));return self.send(run_cli('cancel','--job',data['job']))
                if path=='api/doctor':
                    def check(op):
                        try:
                            result=run_cli('doctor','--quick');workbench.environment={'ok':True,'checked':time.time(),'gpu':result.get('gpu')};return {'ok':True}
                        except Exception as e:
                            workbench.environment={'ok':False,'error':str(e)};raise
                    return self.send({'operation':workbench.begin('doctor',check)})
                self.send({'error':'找不到操作'},404)
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception as e:self.send({'error':str(e)},400)
    return Handler

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    if not sys.flags.isolated or pathlib.Path(sys.executable).resolve()!=PYTHON.resolve():raise RuntimeError('Use the private isolated Python launcher')
    workbench=Workbench();token=secrets.token_urlsafe(24);server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(workbench,token))
    server.daemon_threads=True
    url=f'http://127.0.0.1:{server.server_port}/{token}/';print(json.dumps({'url':url,'service':'subtitle-webui'},ensure_ascii=False),flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close()
        for record in workbench.reviews.values():
            if record['process'].poll() is None:record['process'].terminate()
if __name__=='__main__':main()
