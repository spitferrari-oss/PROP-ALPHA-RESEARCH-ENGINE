#!/usr/bin/env bash
# PARE developer bootstrap (Linux/macOS). See scripts/bootstrap_dev.ps1
# for the Windows equivalent — this project is primarily used on
# Windows, so keep both scripts in sync whenever either changes.
#
# Usage:
#   bash scripts/bootstrap_dev.sh
#
# Override the python binary or venv location if needed:
#   PYTHON_BIN=python3.11 VENV_DIR=.venv bash scripts/bootstrap_dev.sh
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

echo "== PARE dev bootstrap =="

echo "[1/5] Creating virtual environment at ${VENV_DIR}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[2/5] Upgrading pip"
python -m pip install --upgrade pip

echo "[3/5] Installing project + dev dependencies"
pip install -e ".[dev]"

echo "[4/5] Verifying installation (pae system doctor)"
pae system doctor

echo "[5/5] Running a minimal health test"
pae constitution verify
pytest -m "not network and not live" -q tests/test_governance_constitution.py

echo ""
echo "Bootstrap complete."
echo "Activate this environment in new shells with:"
echo "  source ${VENV_DIR}/bin/activate"
echo ""
echo "Copy .env.example to .env and fill in real API keys before using any"
echo "real-provider command (pae options verify-provider, pae data ingest, ...)."
