import pathlib,urllib.request,json,hashlib,zipfile,time
root=pathlib.Path(__file__).resolve().parents[1]
url='https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-full_build-shared.zip'
expected='9f28727e8b472a04c1d2e520aaa425dca82721b995139b35710091130ea6e699'
archive=root/'cache/downloads/ffmpeg-7.1.1-full_build-shared.zip'
if not archive.exists() or hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=expected:
    print('Downloading private FFmpeg 7.1.1 shared',flush=True)
    with urllib.request.urlopen(url,timeout=180) as src,archive.open('wb') as dst:
        while chunk:=src.read(1024*1024):dst.write(chunk)
assert hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()==expected,'FFmpeg checksum mismatch'
dest=root/'runtime/ffmpeg';dest.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
        if not (dest/name).resolve().is_relative_to(dest.resolve()):raise RuntimeError('Unsafe archive path')
    z.extractall(dest)
meta={'version':'7.1.1','url':url,'sha256':expected,'bytes':archive.stat().st_size,'checksum_source':'https://github.com/microsoft/winget-pkgs/blob/master/manifests/g/Gyan/FFmpeg/Shared/7.1.1/Gyan.FFmpeg.Shared.installer.yaml','license':'GPL-3.0-or-later (full shared build); bundled license retained'}
(root/'planning/ffmpeg-source.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
print(json.dumps(meta),flush=True)
