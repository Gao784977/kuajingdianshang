# =============================================================================
# scripts/setup_local.ps1 — Windows PowerShell bootstrap for a fresh checkout
# =============================================================================
# Run once after cloning the repository on a new Windows machine.
# This script does NOT install Python or Git — install those first.
# =============================================================================

param(
    [string]$PythonExe = "python",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "============================================================="
Write-Host "  Opportunity Analysis Tool — local setup (Windows)"
Write-Host "  Project root: $ProjectRoot"
Write-Host "============================================================="

# 1. Verify Python
Write-Host "`n[1/7] Verifying Python..."
& $PythonExe --version
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python not available as '$PythonExe'. Install Python 3.10+ first."
    exit 1
}

# 2. Copy .env.example to .env if missing
Write-Host "`n[2/7] Ensuring .env exists..."
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  Created .env from .env.example."
        Write-Host "  ACTION REQUIRED: edit .env and set ADMIN_BOOTSTRAP_TOKEN."
    } else {
        Write-Error ".env.example missing — cannot continue."
        exit 1
    }
} else {
    Write-Host "  .env already exists."
}

# 3. Create virtual environment (optional but recommended)
Write-Host "`n[3/7] Creating virtual environment (.venv)..."
if (-not (Test-Path ".venv")) {
    & $PythonExe -m venv .venv
    Write-Host "  Created .venv."
} else {
    Write-Host "  .venv already exists."
}
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "  Using venv python: $PythonExe"
}

# 4. Install dependencies
Write-Host "`n[4/7] Installing dependencies..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r requirements.txt

# 5. Create required directories
Write-Host "`n[5/7] Creating required directories..."
$dirs = @("data", "data/web_storage", "data/output", "logs", "temp")
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
        Write-Host "  Created $d"
    } else {
        Write-Host "  $d exists"
    }
}

# 6. Run environment check
Write-Host "`n[6/7] Running environment check..."
& $PythonExe scripts/check_environment.py
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Environment check reported failures — review output above."
}

# 7. Run tests
if (-not $SkipTests) {
    Write-Host "`n[7/7] Running full test suite (this may take ~30s)..."
    & $PythonExe -m unittest discover -s tests -p "test_*.py" 2>&1 | Select-Object -Last 5
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Tests reported failures — review output above."
    }
} else {
    Write-Host "`n[7/7] Skipping tests (-SkipTests)."
}

Write-Host "`n============================================================="
Write-Host "  Setup complete."
Write-Host "  Next steps:"
Write-Host "    1. Edit .env and set ADMIN_BOOTSTRAP_TOKEN"
Write-Host "    2. Start backend: $PythonExe -m backend.app"
Write-Host "    3. Open http://127.0.0.1:8000/"
Write-Host "============================================================="
