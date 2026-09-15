$ErrorActionPreference = 'Stop'
$reconRoot = Split-Path -Parent $PSScriptRoot
$reconBackend = Join-Path $reconRoot 'backend'
$reconFrontend = Join-Path $reconRoot 'frontend'
$reconPython = Join-Path $reconRoot '.venv\Scripts\python.exe'
$reconLogs = Join-Path $reconRoot '.data'

if (-not (Test-Path -LiteralPath $reconPython)) { throw 'Install the Python environment first. See README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $reconFrontend 'node_modules\vite\bin\vite.js'))) { throw 'Run npm.cmd ci inside frontend first.' }
New-Item -ItemType Directory -Force -Path $reconLogs | Out-Null

function Test-ReconPort([int]$Port) {
    $reconSocket = New-Object System.Net.Sockets.TcpClient
    try { $reconSocket.Connect('127.0.0.1', $Port); return $true }
    catch { return $false }
    finally { $reconSocket.Dispose() }
}

if (-not (Test-ReconPort 8765)) {
    Start-Process -FilePath $reconPython -ArgumentList @('-m', 'uvicorn', 'workbench.app:app', '--host', '127.0.0.1', '--port', '8765') -WorkingDirectory $reconBackend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $reconLogs 'backend.out.log') -RedirectStandardError (Join-Path $reconLogs 'backend.err.log') | Out-Null
} else { Write-Host 'Port 8765 is already in use. Existing process was left running.' }

if (-not (Test-ReconPort 5178)) {
    $reconNode = (Get-Command node.exe).Source
    Start-Process -FilePath $reconNode -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1') -WorkingDirectory $reconFrontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $reconLogs 'frontend.out.log') -RedirectStandardError (Join-Path $reconLogs 'frontend.err.log') | Out-Null
} else { Write-Host 'Port 5178 is already in use. Existing process was left running.' }

Write-Host 'Frontend: http://127.0.0.1:5178'
Write-Host 'API docs: http://127.0.0.1:8765/docs'
Write-Host 'If a service does not open, check .data/*.log.'
