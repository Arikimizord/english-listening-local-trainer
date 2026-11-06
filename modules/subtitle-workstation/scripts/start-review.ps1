param([Parameter(Mandatory=$true)][string]$Job)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\environment.ps1"
& "$WorkbenchRoot\envs\subtitle\Scripts\python.exe" -I -B -X utf8 "$PSScriptRoot\review-server.py" --job $Job
exit $LASTEXITCODE
