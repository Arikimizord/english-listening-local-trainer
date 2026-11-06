$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$webuiCliArgs=@($args)
& (Join-Path (Split-Path -Parent $PSScriptRoot) 'workstation.ps1') @webuiCliArgs
exit $LASTEXITCODE
