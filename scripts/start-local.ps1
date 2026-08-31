$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$runtimePython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$pythonExe = if (Test-Path -LiteralPath $runtimePython) { $runtimePython } else { (Get-Command python.exe -ErrorAction Stop).Source }
$nodeExe = (Get-Command node.exe -ErrorAction Stop).Source
$viteEntry = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
$logDir = Join-Path $projectRoot ".local-logs"
$pidFile = Join-Path $projectRoot ".local-pids.json"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$launcherLog = Join-Path $logDir "launcher.log"

function Get-ListeningProcessIds {
    param([int[]]$Ports)
    $portPattern = ($Ports | ForEach-Object { [regex]::Escape($_.ToString()) }) -join "|"
    $ids = foreach ($line in (& netstat.exe -ano -p tcp)) {
        if ($line -match "^\s*TCP\s+\S+:(?:$portPattern)\s+\S+\s+LISTENING\s+(\d+)\s*$") {
            [int]$matches[1]
        }
    }
    @($ids | Sort-Object -Unique)
}

try {
    "$(Get-Date -Format s) launcher started" | Set-Content -LiteralPath $launcherLog -Encoding utf8

    $portsInUse = Get-ListeningProcessIds -Ports @(8000, 5173)
    if ($portsInUse.Count -gt 0) {
        throw "端口 8000 或 5173 已被进程占用（PID: $($portsInUse -join ', ')）。请先运行《停止本地应用.cmd》；若仍存在，再把提示截图发给我。"
    }

    if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
        Write-Host "首次运行：正在安装前端依赖……" -ForegroundColor Cyan
        $npmExe = (Get-Command npm.cmd -ErrorAction Stop).Source
        Push-Location $frontendDir
        try { & $npmExe install } finally { Pop-Location }
    }

    if (-not (Test-Path -LiteralPath $viteEntry)) {
        throw "未找到 Vite 启动文件：$viteEntry"
    }

    $backend = Start-Process -FilePath $pythonExe `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $backendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "backend.out.log") `
        -RedirectStandardError (Join-Path $logDir "backend.err.log") `
        -PassThru

    $frontend = Start-Process -FilePath $nodeExe `
        -ArgumentList @($viteEntry, "--host", "127.0.0.1", "--port", "5173", "--strictPort") `
        -WorkingDirectory $frontendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "frontend.out.log") `
        -RedirectStandardError (Join-Path $logDir "frontend.err.log") `
        -PassThru

    @{
        backend = $backend.Id
        frontend = $frontend.Id
        started_at = (Get-Date).ToString("s")
    } | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8

    $ready = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
            $front = Invoke-WebRequest -Uri "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 2
            if ($health.status -eq "ok" -and $front.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            # Continue polling while both development servers start.
        }
    }

    if (-not $ready) {
        throw "应用未能在 15 秒内启动，请查看 .local-logs 文件夹。"
    }

    "$(Get-Date -Format s) ready backend=$($backend.Id) frontend=$($frontend.Id)" | Add-Content -LiteralPath $launcherLog -Encoding utf8
    Start-Process "http://127.0.0.1:5173/"
    Write-Host "应用已启动：http://127.0.0.1:5173/" -ForegroundColor Green
    Write-Host "浏览器若未自动打开，请复制上面的地址。"
    exit 0
} catch {
    $message = $_.Exception.Message
    "$(Get-Date -Format s) ERROR $message" | Add-Content -LiteralPath $launcherLog -Encoding utf8
    Write-Host "启动失败：$message" -ForegroundColor Red
    Write-Host "诊断日志：$launcherLog" -ForegroundColor Yellow
    exit 1
}
