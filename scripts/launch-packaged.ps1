param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectDir '.venv\Scripts\python.exe'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonExe = if (Test-Path -LiteralPath $venvPython) { $venvPython } elseif (Test-Path -LiteralPath $bundledPython) { $bundledPython } else { (Get-Command python.exe -ErrorAction Stop).Source }
$launcher = Join-Path $PSScriptRoot 'run_packaged.py'
if ($NoBrowser) { & $pythonExe $launcher --no-browser } else { & $pythonExe $launcher }
exit $LASTEXITCODE
