$ErrorActionPreference = 'Stop'
$framework = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$compiler = Join-Path $framework 'csc.exe'
$refs = @('PresentationFramework','PresentationCore','WindowsBase') | ForEach-Object { '/reference:' + (Join-Path $framework "WPF\$_.dll") }
$output = Join-Path $PSScriptRoot 'dist\听力课堂.exe'
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 "/out:$output" @refs /reference:System.Xaml.dll /reference:System.Xml.Linq.dll /reference:System.Web.Extensions.dll ("/resource:" + (Join-Path $PSScriptRoot 'assets\cats-frames.png') + ',CatsFrames') (Join-Path $PSScriptRoot 'src\Player.cs') (Join-Path $PSScriptRoot 'src\LoadingScene.cs')
if ($LASTEXITCODE -ne 0) { throw '编译失败' }
Get-Item -LiteralPath $output | Select-Object FullName, Length
