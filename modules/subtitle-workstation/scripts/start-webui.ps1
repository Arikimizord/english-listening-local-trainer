param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\environment.ps1"
$webuiArgs=@()
if ($NoBrowser) { $webuiArgs+='--no-browser' }
& "$WorkbenchRoot\envs\subtitle\Scripts\python.exe" -I -B -X utf8 "$PSScriptRoot\webui-server.py" @webuiArgs
exit $LASTEXITCODE
