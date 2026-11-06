$ErrorActionPreference='Stop'
. "$PSScriptRoot\environment.ps1"
$uv=Join-Path $WorkbenchRoot 'runtime\uv\uv.exe'
$py=Join-Path $WorkbenchRoot 'envs\subtitle\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $py)){throw 'Private Python environment missing. Bootstrap the pinned runtime first.'}
if(Test-Path -LiteralPath (Join-Path $WorkbenchRoot 'cache\downloads\torch-2.8.0+cu128-cp311-cp311-win_amd64.whl')) { & (Join-Path $PSScriptRoot 'install-local-torch.ps1') }
& $uv pip sync (Join-Path $WorkbenchRoot 'config\requirements-win-py311.lock') --python $py --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match --require-hashes --no-build
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $uv pip check --python $py
exit $LASTEXITCODE
