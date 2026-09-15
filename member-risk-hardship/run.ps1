param([int]$Port = 8017)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Test-Path -LiteralPath '.vendor') {
    $env:PYTHONPATH = "$PSScriptRoot\.vendor;$PSScriptRoot"
}
$riskPython = 'python'
if (Test-Path -LiteralPath '.venv\Scripts\python.exe') {
    $riskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}
& $riskPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --workers 1
