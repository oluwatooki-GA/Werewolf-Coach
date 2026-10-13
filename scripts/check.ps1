# Mirrors the "Checked by" column of CONSTRAINTS.md. If they differ, CONSTRAINTS.md wins.
# Usage: powershell -File scripts/check.ps1 fast|task|full
param([ValidateSet('fast', 'task', 'full')][string]$Level = 'fast')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot)

function Step([string]$name, [scriptblock]$cmd) {
    Write-Host "== $name"
    & $cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $name"; exit 1 }
}

# The floor runs at every level, with or without a project.
Step 'floor guard' { uv run --no-project python scripts/floor_guard.py }

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
