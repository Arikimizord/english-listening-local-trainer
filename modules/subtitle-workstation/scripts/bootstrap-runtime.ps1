$ErrorActionPreference='Stop'
. "$PSScriptRoot\environment.ps1"
$root=$WorkbenchRoot
$uvZip=Join-Path $root 'cache\downloads\uv-0.13.6-win-x64.zip'
$url='https://github.com/astral-sh/uv/releases/download/0.13.6/uv-x86_64-pc-windows-msvc.zip'
$expected='a2a8820d5eea32f08ef467ef3b7f66883a9b076d5737a2fc2fbb5f458d1bb50f'
if(-not(Test-Path -LiteralPath $uvZip)) { Invoke-WebRequest -Uri $url -OutFile $uvZip }
if((Get-FileHash -LiteralPath $uvZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected){throw 'uv archive checksum mismatch'}
Expand-Archive -LiteralPath $uvZip -DestinationPath (Join-Path $root 'runtime\uv') -Force
$uv=Join-Path $root 'runtime\uv\uv.exe'
if(-not(Test-Path -LiteralPath $uv)) {throw 'uv executable not found'}
& $uv --version
if($LASTEXITCODE -ne 0){throw 'uv failed'}
& $uv python install 3.11.18 --no-bin --no-registry
if($LASTEXITCODE -ne 0){throw 'Private Python installation failed'}
$py=@(Get-ChildItem -LiteralPath $env:UV_PYTHON_INSTALL_DIR -Filter python.exe -Recurse | Where-Object {$_.FullName -notlike '*\Scripts\*'})
if($py.Count -ne 1){throw 'Private interpreter discovery ambiguous'}
if(-not(Test-Path -LiteralPath (Join-Path $root 'envs\subtitle\Scripts\python.exe'))) { & $uv venv --python $py[0].FullName (Join-Path $root 'envs\subtitle') }
if($LASTEXITCODE -ne 0){throw 'Private venv creation failed'}
& (Join-Path $root 'envs\subtitle\Scripts\python.exe') -I -X utf8 -c 'import sys,site,json; print(json.dumps({"executable":sys.executable,"version":sys.version,"user_site_enabled":site.ENABLE_USER_SITE,"prefix":sys.prefix,"base_prefix":sys.base_prefix},ensure_ascii=False))'
if($LASTEXITCODE -ne 0){throw 'Private interpreter validation failed'}
