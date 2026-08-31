@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch-packaged.ps1"
if errorlevel 1 pause
