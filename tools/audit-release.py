"""Audit tracked/staged release candidates; never prints matching secret values."""
from pathlib import Path
import hashlib,json,re,sys,subprocess
ROOT=Path(__file__).resolve().parents[1]
EXCLUDE={'.git','envs','models','runtime','cache','temp','jobs','ui','__pycache__'}
MEDIA={'.mp3','.m4a','.wav','.aac','.flac','.srt','.ass'}
PATTERNS={
 'private_key':r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',
 'github_token':r'\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}',
 'aws_key':r'\bAKIA[A-Z0-9]{16}\b',
 'api_key':r'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}',
 'personal_path':r'[A-Z]:\\(?:Users|ClaudeCode|Cline)\\',
}
def candidates():
 if (ROOT/'.git').exists():
  result=subprocess.run(['git','ls-files','--cached','-z'],cwd=ROOT,capture_output=True,check=True)
  return [ROOT/p for p in result.stdout.decode('utf-8').split('\0') if p]
 return [p for p in ROOT.rglob('*') if p.is_file() and not set(p.relative_to(ROOT).parts)&EXCLUDE]
def main():
 files=candidates();findings=[];manifest=[]
 for p in sorted(files):
  rel=p.relative_to(ROOT);name=rel.as_posix()
  if set(rel.parts)&EXCLUDE or p.suffix.lower() in MEDIA or p.name.startswith('.env') or p.suffix.lower() in {'.pem','.key','.pfx','.log','.zip'}:
   findings.append({'path':name,'kind':'excluded_file'});continue
  data=(subprocess.run(['git','show',':'+name],cwd=ROOT,capture_output=True,check=True).stdout if (ROOT/'.git').exists() else p.read_bytes())
  if p.suffix.lower() not in {'.exe','.png','.gif'}:
   text=data.decode('utf-8-sig',errors='replace')
   for kind,pattern in PATTERNS.items():
    if re.search(pattern,text):findings.append({'path':name,'kind':kind})
  if name not in {'docs/source-manifest.json','docs/automated-audit.json'}:
   manifest.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
 report={'candidate_count':len(files),'findings':findings,'scope':'allowlisted release files; pattern scanning is not a guarantee that all sensitive content has been detected'}
 (ROOT/'docs/automated-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (ROOT/'docs/source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False));return 1 if findings else 0
if __name__=='__main__':sys.exit(main())
