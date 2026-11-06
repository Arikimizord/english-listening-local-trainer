@echo off
chcp 65001 >nul
title 高精度字幕工作站
powershell.exe -NoProfile -File "%~dp0scripts\start-webui.ps1" %*
if errorlevel 1 pause
