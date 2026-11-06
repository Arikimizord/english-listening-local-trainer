@echo off
setlocal DisableDelayedExpansion
pwsh -NoProfile -File "%~dp0workstation.ps1" %*
exit /b %errorlevel%
