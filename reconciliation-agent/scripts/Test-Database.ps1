$ErrorActionPreference = 'Stop'
$reconRoot = Split-Path -Parent $PSScriptRoot
$reconValues = @{}
Get-Content -LiteralPath (Join-Path $reconRoot '.data/postgres-test.env') | ForEach-Object {
    $reconParts = $_.Split('=', 2)
    $reconValues[$reconParts[0]] = $reconParts[1]
}
$env:RECON_DATABASE_URL = 'postgresql+psycopg://' + $reconValues['POSTGRES_USER'] + ':' + $reconValues['POSTGRES_PASSWORD'] + '@127.0.0.1:55432/' + $reconValues['POSTGRES_DB']
$env:RECON_REQUIRE_DATABASE_TESTS = '1'
$env:PYTHONPATH = Join-Path $reconRoot 'backend'
Push-Location (Join-Path $reconRoot 'backend')
try {
    & (Join-Path $reconRoot '.venv/Scripts/python.exe') -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $reconRoot '.venv/Scripts/python.exe') -m pytest tests -q -p no:cacheprovider
    exit $LASTEXITCODE
} finally { Pop-Location }
