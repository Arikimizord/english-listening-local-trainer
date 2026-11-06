"""No-model stage-4 contract tests; all fixtures stay in a unique temp subtree."""
import pathlib,sys,importlib.util,unittest,uuid,json,concurrent.futures,os
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('stage4_core_tests',ROOT/'scripts/workstation-core.py')
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
import subtitle_formats as fmt
BASE=ROOT/'temp'/('stage4-unit-'+uuid.uuid4().hex);BASE.mkdir(parents=True)
core.JOBS=BASE/'jobs';core.JOBS.mkdir()

class Contracts(unittest.TestCase):
 def setUp(self):
  self.fingerprint=mock.patch.object(core,'code_fingerprint',return_value='unit-pipeline-v1');self.fingerprint.start();self.addCleanup(self.fingerprint.stop)
  self.models=mock.patch.object(core,'models_check',return_value=[]);self.models.start();self.addCleanup(self.models.stop)
 def fixture(self,missing=False):
  source=BASE/(uuid.uuid4().hex+'.wav');source.write_bytes(b'unit-only-no-decoding')
  cfg={'schema_version':1,'audio':str(source),'language':'en','reference_text':None,'reference_segments':None,'timeout_seconds':10}
  p=core.createjob({'configuration':cfg,'audio_sha256':core.sha(source),'duration_seconds':2.0,'warnings':[]})
  s=core.loadjob(p)
  words=[{'word':'Hello','start':0.1,'end':0.7},{'word':'world','start':0.9,'end':1.6}]
  if missing:words[1].pop('start');words[1].pop('end')
  payload={'schema_version':1,'stage':'asr','device':'cuda','segments':[{'start':0.0,'end':2.0,'text':'Hello world','words':words}]}
  core.atomic(p/'asr.json',payload)
  fp=core.digest({'audio':s['audio_sha256'],'pipeline':core.code_fingerprint(),'language':'en'})
  s['stages']['asr']={'status':'completed','fingerprint':fp,'files':{'asr.json':core.sha(p/'asr.json')}}
  core.savejob(p,s);self.seed_align(p,s,payload);return p,s
 def seed_align(self,p,s,payload=None):
  effective=core.alignment_input(p,s)
  if payload is None:payload={'schema_version':1,'stage':'align','device':'cuda','segments':effective['segments']}
  payload=dict(payload);payload['stage']='align';core.atomic(p/'align.json',payload)
  fp=core.digest({'asr':core.sha(p/'asr.json'),'input':effective,'pipeline':core.code_fingerprint()})
  s['stages']['align']={'status':'completed','fingerprint':fp,'files':{'align.json':core.sha(p/'align.json')},'input_sha':core.sha(p/'alignment-input.json')}
  core.savejob(p,s)
 def patchfile(self,p,text):
  q=BASE/(uuid.uuid4().hex+'.json');q.write_text(json.dumps({'schema_version':1,'base_transcript_sha256':core.sha(p/'asr.json'),'segment_text':{'0':text}}),encoding='utf-8');return q
 def fault(self,code,fn,*args):
  with self.assertRaises(core.Fault) as caught:fn(*args)
  self.assertEqual(caught.exception.code,code)
 def test_valid_export_and_cache(self):
  p,s=self.fixture();out=core.export_job(p,s);self.assertIn('subtitles.srt',out);self.assertEqual(core.export_job(p,s),out)
  self.assertEqual(core.read(pathlib.Path(out['manifest.json']))['review_status'],'pending')
 def test_export_rejects_audio_mutation(self):
  p,s=self.fixture();(p/s['audio_snapshot']).write_bytes(b'changed');self.fault(7,core.export_job,p,s)
 def test_export_rejects_code_change(self):
  p,s=self.fixture()
  with mock.patch.object(core,'code_fingerprint',return_value='unit-pipeline-v2'):self.fault(7,core.export_job,p,s)
 def test_export_rejects_asr_corruption(self):
  p,s=self.fixture();x=core.read(p/'asr.json');x['segments'][0]['text']='changed';core.atomic(p/'asr.json',x);self.fault(7,core.export_job,p,s)
 def test_patch_immutable_and_invalidates(self):
  p,s=self.fixture();q=self.patchfile(p,'Hello corrected');one=core.review(p,str(q));stored=pathlib.Path(one['patch']);first=stored.read_bytes()
  q2=self.patchfile(p,'Hello twice');two=core.review(p,str(q2));self.assertNotEqual(one['patch'],two['patch']);self.assertEqual(stored.read_bytes(),first)
  s=core.loadjob(p);self.assertEqual(s['status'],'needs_realign');self.assertEqual(s['owner_review'],'pending');self.assertEqual(s['outputs'],{});self.fault(7,core.export_job,p,s)
 def test_changed_applied_patch_cannot_export_old_alignment(self):
  p,s=self.fixture();applied=core.review(p,str(self.patchfile(p,'Hello revised')));s=core.loadjob(p);self.seed_align(p,s)
  path=pathlib.Path(applied['patch']);x=core.read(path);x['segment_text']['0']='Changed after alignment';core.atomic(path,x);self.fault(7,core.export_job,p,s)
 def test_patch_base_conflict(self):
  p,s=self.fixture();q=self.patchfile(p,'Hello revised');x=core.read(q);x['base_transcript_sha256']='0'*64;q.write_text(json.dumps(x),encoding='utf-8');self.fault(7,core.review,p,str(q));self.assertEqual(core.loadjob(p)['patches'],[])
 def test_invalid_ids(self):
  for bad in ['../escape','A'*32,'x','a'*31,'a'*33,'']:
   with self.subTest(bad=bad):self.fault(2,core.jobdir,bad)
 def test_path_and_atomic_reject_escape(self):
  dest=BASE/'not-in-jobs.json';self.fault(2,core.path_in,dest,core.JOBS);self.fault(2,core.atomic,dest,{'bad':True});self.assertFalse(dest.exists())
 def test_mutex_same_process_thread_contention(self):
  lock=core.JOBS/'unit-exclusive.lock'
  with core.mutex(lock):
   def contender():
    try:
     with core.mutex(lock):return 'unexpectedly acquired'
    except core.Fault as e:return e.code
   with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:self.assertEqual(pool.submit(contender).result(timeout=4),4)
  with core.mutex(lock):pass
 def test_review_rejects_live_worker(self):
  p,s=self.fixture();s['worker_pid']=os.getpid();core.savejob(p,s);self.fault(4,core.review,p);self.fault(4,core.export_job,p,s)
 def test_cancel_only_requests_no_process_kill(self):
  p,s=self.fixture();s['status']='running';s['worker_pid']=987654;core.savejob(p,s)
  with mock.patch.object(sys,'argv',['workstation','cancel','--job',p.name]),mock.patch.object(core.subprocess,'Popen',side_effect=AssertionError('No child launch or kill here')):
   result=core.main()
  self.assertTrue(result['cancel_requested']);self.assertTrue((p/'cancel.request').is_file());self.assertEqual(core.loadjob(p)['owner_review'],'pending')
 def test_missing_word_times_stay_missing_and_ass_falls_back(self):
  raw={'segments':[{'start':0,'end':2,'text':'Hello world','words':[{'word':'Hello','start':0.1,'end':0.7},{'word':'world'}]}]}
  n=fmt.normalize_and_validate(raw,2);self.assertIsNone(n['segments'][0]['words'][1]['start_ms']);ass=fmt.render_ass(n);self.assertNotIn(r'{\k',ass)
  self.assertIn('ass_sentence_fallback_missing_times',[w['code'] for w in n['warnings']])
 def test_ass_override_tags_are_escaped(self):
  n=fmt.normalize_and_validate({'segments':[{'start':0,'end':2,'text':r'{\pos(1,2)}Hello\Nworld'}]},2)
  ass=fmt.render_ass(n);self.assertNotIn(r'{\pos',ass);self.assertNotIn(r'Hello\Nworld',ass);self.assertIn('｛',ass)
 def test_invalid_time_not_silently_accepted(self):
  for start,end in [(float('nan'),1),(0,float('inf')),(2,1),(-1,1),(0,3)]:
   with self.subTest(start=start,end=end),self.assertRaises(ValueError):fmt.normalize_and_validate({'segments':[{'start':start,'end':end,'text':'Hello'}]},2)
 def test_dict_warnings_export_success(self):
  p,s=self.fixture(missing=True);out=core.export_job(p,s);self.assertIn('subtitles.ass',out);self.assertTrue(any(isinstance(w,dict) for w in s['warnings']))

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Contracts)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 report={'ok':result.wasSuccessful(),'tests_run':result.testsRun,'failures':[{'test':str(t),'traceback':msg} for t,msg in result.failures],'errors':[{'test':str(t),'traceback':msg} for t,msg in result.errors],'fixture_root':str(BASE),'models_executed':False}
 (BASE/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False));sys.exit(0 if report['ok'] else 1)
