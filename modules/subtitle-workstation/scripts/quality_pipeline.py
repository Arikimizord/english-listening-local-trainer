"""Offline audio-grounded quality pass for existing job transcripts.

Owns locks, immutable evidence, and integrity-checked caching; no cloud service.
"""
import hashlib,json,pathlib,subprocess,sys,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
from boundary_repair import candidates,apply_to_normalized,recheck_evidence

def repair_document(job,document,core):
    state=core.loadjob(job);audio=job/state['audio_snapshot'];source=job/'asr.json'
    if core.sha(audio)!=state['audio_sha256']:raise ValueError('Audio hash mismatch')
    if core.sha(source)!=state['stages']['asr']['files']['asr.json']:raise ValueError('ASR hash mismatch')
    raw=core.read(source)
    if not candidates(raw['segments']):return document
    key=core.digest({'asr':core.sha(source),'audio':core.sha(audio),
                     'worker':core.sha(ROOT/'scripts/pipeline-worker.py'),
                     'repair':core.sha(ROOT/'scripts/boundary_repair.py')})
    folder=job/'quality-work'/key;report=folder/'result.json';manifest=folder/'manifest.json'
    def cached():
        return report.is_file() and manifest.is_file() and core.read(manifest).get('result_sha256')==core.sha(report)
    with core.mutex(job/'run.lock'),core.mutex(ROOT/'jobs/gpu.lock'):
        core.no_orphan(core.loadjob(job))
        if not cached():
            folder.mkdir(parents=True,exist_ok=True)
            # Reuse only hash-verified contextual decodes from the same source
            # and decoder. Re-evaluate decisions with the current rule below.
            for receipt in (job/'quality-work').glob('*/context-provenance.json'):
                proof=core.read(receipt);old=receipt.parent/'result.json'
                if (proof.get('asr_sha256')==core.sha(source) and proof.get('audio_sha256')==state['audio_sha256']
                    and proof.get('worker_sha256')==core.sha(ROOT/'scripts/pipeline-worker.py')
                    and old.is_file() and proof.get('result_sha256')==core.sha(old)):
                    core.atomic(report,core.read(old))
                    core.atomic(manifest,{'key':key,'result_sha256':core.sha(report),'audio_sha256':state['audio_sha256'],'reused_contexts':str(old)})
                    break
        if not cached():
            args=[sys.executable,'-I','-B','-X','utf8',str(ROOT/'scripts/pipeline-worker.py'),
                  '--stage','repair','--audio',str(audio),'--segments',str(source),'--output',str(report)]
            with (folder/'worker.log').open('w',encoding='utf-8') as log:
                child=subprocess.Popen(args,stdout=log,stderr=log)
                lock=core.read(ROOT/'jobs/gpu.lock');lock['child_pid']=child.pid;core.atomic(ROOT/'jobs/gpu.lock',lock)
                try:code=child.wait(timeout=600)
                except subprocess.TimeoutExpired:child.kill();child.wait();raise ValueError('Offline quality pass timed out')
            if code:raise ValueError('Offline quality pass failed: '+str(folder/'worker.log'))
            data=core.read(report)
            if data['audio_sha256']!=state['audio_sha256']:raise ValueError('Repair result audio mismatch')
            core.atomic(manifest,{'key':key,'result_sha256':core.sha(report),'audio_sha256':state['audio_sha256']})
            core.atomic(folder/'context-provenance.json',{'asr_sha256':core.sha(source),'audio_sha256':state['audio_sha256'],'worker_sha256':core.sha(ROOT/'scripts/pipeline-worker.py'),'result_sha256':core.sha(report)})
        data=core.read(report)
    evidence=recheck_evidence(data['boundary_repair'])
    if any(x['action']=='retain_unconfirmed' for x in evidence):
        raise ValueError('Local contextual decodes disagree; quality pass did not converge')
    result=apply_to_normalized(document,evidence)
    result['quality_evidence']=str(report)
    return result
