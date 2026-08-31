@echo off
chcp 65001 >nul
title 科学视觉传播智能体 - 本地启动器
cd /d "%~dp0"
echo 正在启动，请稍候...
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1"
if errorlevel 1 (
  echo.
  echo 启动失败，请截图本窗口或查看 .local-logs\launcher.log。
  pause
  exit /b 1
)
echo 启动成功，此窗口可以关闭。
timeout /t 3 >nul
