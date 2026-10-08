#!/usr/bin/env bash
# =============================================================================
# scripts/setup_local.sh — macOS/Linux bootstrap for a fresh checkout
# =============================================================================
# Run once after cloning the repository on a new macOS/Linux machine.
# This script does NOT install Python or Git — install those first.
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_EXE="${PYTHON:-python3}"

echo "============================================================="
echo "  Opportunity Analysis Tool — local setup (macOS/Linux)"
echo "  Project root: $PROJECT_ROOT"
echo "============================================================="

# 1. Verify Python
echo -e "\n[1/7] Verifying Python..."
"$PYTHON_EXE" --version

# 2. Copy .env.example to .env if missing
echo -e "\n[2/7] Ensuring .env exists..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp ".env.example" ".env"
        echo "  Created .env from .env.example."
        echo "  ACTION REQUIRED: edit .env and set ADMIN_BOOTSTRAP_TOKEN."
    else
        echo "ERROR: .env.example missing — cannot continue." >&2
        exit 1
    fi
else
    echo "  .env already exists."
fi

# 3. Create virtual environment (optional but recommended)
echo -e "\n[3/7] Creating virtual environment (.venv)..."
if [ ! -d ".venv" ]; then
    "$PYTHON_EXE" -m venv .venv
    echo "  Created .venv."
else
    echo "  .venv already exists."
fi
if [ -f ".venv/bin/python" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/bin/python"
    echo "  Using venv python: $PYTHON_EXE"
fi

# 4. Install dependencies
echo -e "\n[4/7] Installing dependencies..."
"$PYTHON_EXE" -m pip install --upgrade pip
"$PYTHON_EXE" -m pip install -r requirements.txt

# 5. Create required directories
echo -e "\n[5/7] Creating required directories..."
for d in data data/web_storage data/output logs temp; do
    if [ ! -d "$d" ]; then
        mkdir -p "$d"
        echo "  Created $d"
    else
        echo "  $d exists"
    fi
done

# 6. Run environment check
echo -e "\n[6/7] Running environment check..."
"$PYTHON_EXE" scripts/check_environment.py || echo "WARNING: environment check reported failures."

# 7. Run tests
if [ "${SKIP_TESTS:-0}" != "1" ]; then
    echo -e "\n[7/7] Running full test suite (this may take ~30s)..."
    "$PYTHON_EXE" -m unittest discover -s tests -p "test_*.py" 2>&1 | tail -n 5 || echo "WARNING: tests reported failures."
else
    echo -e "\n[7/7] Skipping tests (SKIP_TESTS=1)."
fi

echo -e "\n============================================================="
echo "  Setup complete."
echo "  Next steps:"
echo "    1. Edit .env and set ADMIN_BOOTSTRAP_TOKEN"
echo "    2. Start backend: $PYTHON_EXE -m backend.app"
echo "    3. Open http://127.0.0.1:8000/"
echo "============================================================="
