$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$cliArgs=@($args)
$before=[Environment]::GetEnvironmentVariables('Process')
$oldLocation=Get-Location
$code=5
try {
 . (Join-Path $root 'scripts\environment.ps1')
 $env:HF_HUB_OFFLINE='1';$env:TRANSFORMERS_OFFLINE='1'
 & (Join-Path $root 'envs\subtitle\Scripts\python.exe') -I -X utf8 (Join-Path $root 'scripts\workstation-bootstrap.py') @cliArgs
 $code=$LASTEXITCODE
} catch {
 @{schema_version=1;ok=$false;review_status='pending';outputs=@{};warnings=@();errors=@(@{code=3;message=$_.Exception.Message})} | ConvertTo-Json -Depth 8 -Compress
 $code=3
} finally {
 foreach($key in @([Environment]::GetEnvironmentVariables('Process').Keys)) {if(-not $before.Contains($key)){Remove-Item -LiteralPath ('Env:\'+$key) -ErrorAction SilentlyContinue}}
 foreach($key in $before.Keys){[Environment]::SetEnvironmentVariable($key,$before[$key],'Process')}
 Set-Location -LiteralPath $oldLocation.Path
}
exit $code
