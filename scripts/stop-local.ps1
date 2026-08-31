$ErrorActionPreference = "SilentlyContinue"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot ".local-pids.json"

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "没有找到本项目的运行记录，应用可能已经停止。" -ForegroundColor Yellow
    Read-Host "按 Enter 退出"
    exit 0
}

$processes = Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json
foreach ($processId in @($processes.backend, $processes.frontend)) {
    if ($processId) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

Start-Sleep -Milliseconds 500

Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "本地前端和后端已经停止。" -ForegroundColor Green
Read-Host "按 Enter 退出"
