param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
}
$LumaBuild = Get-Item -LiteralPath 'web\dist\index.html' -ErrorAction SilentlyContinue
$LumaSources = Get-ChildItem -LiteralPath 'web\src' -Recurse -File
$LumaNewest = ($LumaSources + (Get-Item -LiteralPath 'web\package-lock.json')) | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $LumaBuild -or $LumaNewest.LastWriteTimeUtc -gt $LumaBuild.LastWriteTimeUtc) {
    Push-Location -LiteralPath 'web'
    npm.cmd ci
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    Pop-Location
}
& '.\.venv\Scripts\python.exe' -m backend.migrations
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
& '.\.venv\Scripts\python.exe' -m scripts.seed
& '.\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
