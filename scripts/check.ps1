# Usage: powershell -File scripts/check.ps1 fast|task|full
param([ValidateSet('fast', 'task', 'full')][string]$Level = 'fast')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot)

function Step([string]$name, [scriptblock]$cmd) {
    Write-Host "== $name"
    $global:LASTEXITCODE = 0
    & $cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $name"; exit 1 }
}

# Python checks need pyproject.toml, which M1 task 1 creates. Say so loudly instead of passing silently.
if (-not (Test-Path pyproject.toml)) {
    Write-Host 'NOT RUN: ruff, mypy, pytest (no pyproject.toml yet; M1 task 1 creates it)'
    exit 0
}
Step 'architecture test exists' { if (-not (Test-Path tests/test_architecture.py)) { Write-Host 'missing tests/test_architecture.py'; $global:LASTEXITCODE = 1 } }
Step 'ruff' { uv run ruff check . }
Step 'mypy' { uv run mypy src }
if ($Level -ne 'fast') { Step 'pytest' { uv run pytest -q } }
Write-Host "check:$Level passed"
