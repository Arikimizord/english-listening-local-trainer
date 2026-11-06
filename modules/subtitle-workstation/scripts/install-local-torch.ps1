$ErrorActionPreference='Stop'
. "$PSScriptRoot\environment.ps1"
$wheel=Join-Path $WorkbenchRoot 'cache\downloads\torch-2.8.0+cu128-cp311-cp311-win_amd64.whl'
$hash='34c55443aafd31046a7963b63d30bc3b628ee4a704f826796c865fdfd05bb596'
if((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash){throw 'Local Torch wheel checksum mismatch'}
$req='torch @ '+([Uri]$wheel).AbsoluteUri+' --hash=sha256:'+$hash
$req | Set-Content -LiteralPath (Join-Path $WorkbenchRoot 'temp\local-torch.lock') -Encoding utf8
& (Join-Path $WorkbenchRoot 'runtime\uv\uv.exe') pip install --python (Join-Path $WorkbenchRoot 'envs\subtitle\Scripts\python.exe') --offline --no-index --no-deps --require-hashes -r (Join-Path $WorkbenchRoot 'temp\local-torch.lock')
if($LASTEXITCODE -ne 0){throw 'Verified local Torch install failed'}
