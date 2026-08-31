# PARE developer bootstrap (Windows PowerShell). This project is
# primarily used on Windows -- this is the primary bootstrap path, kept
# in sync with scripts/bootstrap_dev.sh (Linux/macOS).
#
# Usage (from the repository root, in PowerShell):
#   .\scripts\bootstrap_dev.ps1
#
# If script execution is blocked by PowerShell's execution policy, run
# once (as the current user, not admin):
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#
# Override the python launcher or venv location if needed:
#   $env:PYTHON_BIN = "python"; $env:VENV_DIR = ".venv"; .\scripts\bootstrap_dev.ps1

$ErrorActionPreference = "Stop"

$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "py" }
$VenvDir = if ($env:VENV_DIR) { $env:VENV_DIR } else { ".venv" }
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "== PARE dev bootstrap ==" -ForegroundColor Cyan

Write-Host "[1/5] Creating virtual environment at $VenvDir"
& $PythonBin -m venv $VenvDir

$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
Write-Host "[2/5] Activating virtual environment"
. $ActivateScript

Write-Host "[3/5] Upgrading pip"
python -m pip install --upgrade pip

Write-Host "[4/5] Installing project + dev dependencies"
pip install -e ".[dev]"

Write-Host "[5/5] Verifying installation (pae system doctor)"
pae system doctor

Write-Host ""
Write-Host "Running a minimal health test"
pae constitution verify
pytest -m "not network and not live" -q tests/test_governance_constitution.py

Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Green
Write-Host "Activate this environment in a new PowerShell session with:"
Write-Host "  $ActivateScript"
Write-Host ""
Write-Host "Copy .env.example to .env and fill in real API keys before using any"
Write-Host "real-provider command (pae options verify-provider, pae data ingest, ...)."
