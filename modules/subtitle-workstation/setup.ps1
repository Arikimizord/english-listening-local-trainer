# Run in a fresh child PowerShell. Downloads pinned upstream dependencies and models.
[CmdletBinding()]
param([switch]$SkipModels)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
if(-not [Environment]::Is64BitOperatingSystem){throw 'Windows x64 is required'}
foreach($relative in @('cache/downloads','runtime','envs','models','temp','jobs','ui','planning/logs','planning/stage3/samples')){
 New-Item -ItemType Directory -Force -Path (Join-Path $root $relative) | Out-Null
}
. (Join-Path $root 'scripts/environment.ps1')
function Run-Python([string]$Script){
 & (Join-Path $root 'envs/subtitle/Scripts/python.exe') -I -B -X utf8 (Join-Path $root ('scripts/'+$Script))
 if($LASTEXITCODE -ne 0){throw ('Failed: '+$Script)}
}
& (Join-Path $root 'scripts/bootstrap-runtime.ps1')
Run-Python 'download-torch-wheel.py'
# Installs the verified cached Torch wheel before syncing all hashed requirements.
& (Join-Path $root 'scripts/rebuild-environment.ps1')
if($LASTEXITCODE -ne 0){throw 'Locked dependency installation failed'}
Run-Python 'install-private-ffmpeg.py'
if($SkipModels){Write-Host 'Runtime prepared. Run setup.ps1 without -SkipModels to install pinned models before production.';exit 0}
Run-Python 'download-stage3-models.py'
& (Join-Path $root 'workstation.ps1') doctor --json
if($LASTEXITCODE -ne 0){throw 'Doctor failed; preserve its error output'}
Write-Host 'Installation checks complete. Start 字幕工作站.cmd and review generated subtitles before classroom use.'
