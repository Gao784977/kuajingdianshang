#!/usr/bin/env python3
"""Local environment checker for multi-device development.

Run on each machine (company laptop, personal laptop, CI) to verify the
project is ready for development. Uses only the Python standard library.

Usage:
    python scripts/check_environment.py

Exit codes:
    0  — all checks PASS
    1  — one or more checks FAIL
    2  — script invoked incorrectly
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

# Resolve project root from this script's location (scripts/check_environment.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Ensure project root is importable so "import backend" works when run from
# anywhere (scripts/ is a subdir; sys.path[0] would otherwise be scripts/).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Configuration (must match backend/config.py defaults)
# ---------------------------------------------------------------------------
MIN_PYTHON = (3, 10)
REQUIRED_DIRS = ["data", "data/web_storage", "data/output", "logs", "temp"]
CONFIG_FILES = [
    "config/opportunity_config.json",
    "config/amazon_workflow.json",
]
LOCK_FILES = ["requirements.txt"]
ENV_EXAMPLE = ".env.example"
ENV_FILE = ".env"
DEFAULT_PORT = int(os.environ.get("PORT", "8000"))
SQLITE_PATH = Path(os.environ.get("SQLITE_PATH", "data/web.db"))
WEB_STORAGE = Path(os.environ.get("WEB_STORAGE_DIR", "data/web_storage"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "data/output"))

# Patterns that indicate a real secret leaked into source/config files.
# Match key names, not values — never print the value itself.
SECRET_NAME_PATTERNS = (
    "API_KEY", "ACCESS_KEY", "SECRET_KEY", "AWS_SECRET",
    "OPENAI_API_KEY", "AMAZON_SECRET", "SESSION_SECRET", "CSRF_SECRET",
    "ADMIN_BOOTSTRAP_TOKEN", "GITHUB_TOKEN", "SLACK_TOKEN",
)
SECRET_VALUE_HINTS = (
    "sk-", "AKIA", "ghp_", "gho_", "xoxb-", "Bearer ",
)
# Files that are allowed to reference secret names (documentation / templates).
SECRET_SCAN_ALLOWLIST = {
    ".env.example",
    "scripts/check_environment.py",
    "scripts/reset_local_data.py",
    "docs/AI_DEVELOPMENT_CONTEXT.md",
    "docs/LOCAL_SETUP.md",
    "docs/MULTI_DEVICE_DEVELOPMENT.md",
    "docs/GIT_SETUP.md",
    "CONTRIBUTING.md",
    "README.md",
    "backend/config.py",
    "handoff/SECURITY_STATUS.md",
    "handoff/DECISIONS.md",
}


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def check_python_version() -> bool:
    v = sys.version_info
    if (v.major, v.minor) >= MIN_PYTHON:
        _ok(f"Python {v.major}.{v.minor}.{v.micro} >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
        return True
    _fail(f"Python {v.major}.{v.minor}.{v.micro} < required {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
    return False


def check_optional_dependency() -> bool:
    try:
        import openpyxl  # noqa: F401
        _ok("openpyxl importable (Excel output enabled)")
        return True
    except ImportError:
        _warn("openpyxl not installed — Excel output will be skipped (MD/JSON still work)")
        return True  # optional dependency, not a hard failure


def check_backend_importable() -> bool:
    try:
        import backend  # noqa: F401
        _ok("backend package importable")
        return True
    except Exception as exc:  # pragma: no cover - environment specific
        _fail(f"backend package not importable: {exc!r}")
        return False


def check_config_files() -> bool:
    ok = True
    for rel in CONFIG_FILES:
        path = PROJECT_ROOT / rel
        if path.is_file():
            _ok(f"{rel} exists")
        else:
            _fail(f"{rel} missing")
            ok = False
    return ok


def check_lock_files() -> bool:
    ok = True
    for rel in LOCK_FILES:
        path = PROJECT_ROOT / rel
        if path.is_file():
            _ok(f"{rel} exists")
        else:
            _fail(f"{rel} missing")
            ok = False
    return ok


def check_env_example() -> bool:
    path = PROJECT_ROOT / ENV_EXAMPLE
    if path.is_file():
        _ok(f"{ENV_EXAMPLE} exists (template for local .env)")
        return True
    _fail(f"{ENV_EXAMPLE} missing — cannot bootstrap local .env safely")
    return False


def check_required_dirs() -> bool:
    ok = True
    for rel in REQUIRED_DIRS:
        path = PROJECT_ROOT / rel
        if path.is_dir():
            _ok(f"{rel}/ exists")
        else:
            try:
                path.mkdir(parents=True, exist_ok=True)
                _ok(f"{rel}/ created")
            except OSError as exc:
                _fail(f"{rel}/ cannot be created: {exc!r}")
                ok = False
    return ok


def check_writable_sqlite() -> bool:
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    test_file = SQLITE_PATH.parent / ".write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        _ok(f"SQLite path writable: {SQLITE_PATH}")
        return True
    except OSError as exc:
        _fail(f"SQLite path not writable: {SQLITE_PATH} ({exc!r})")
        return False


def check_writable_storage() -> bool:
    WEB_STORAGE.mkdir(parents=True, exist_ok=True)
    test_file = WEB_STORAGE / ".write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        _ok(f"Web storage writable: {WEB_STORAGE}")
        return True
    except OSError as exc:
        _fail(f"Web storage not writable: {WEB_STORAGE} ({exc!r})")
        return False


def check_writable_output() -> bool:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    test_file = OUTPUT_DIR / ".write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        _ok(f"Output directory writable: {OUTPUT_DIR}")
        return True
    except OSError as exc:
        _fail(f"Output directory not writable: {OUTPUT_DIR} ({exc!r})")
        return False


def check_port_available() -> bool:
    # Best-effort: bind to 127.0.0.1:PORT to see if it is free.
    # Not a guarantee under concurrent startup, but catches obvious conflicts.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", DEFAULT_PORT))
        _ok(f"Port {DEFAULT_PORT} available on 127.0.0.1")
        return True
    except OSError:
        _warn(f"Port {DEFAULT_PORT} appears to be in use — backend startup may fail")
        return True  # warning, not failure — the port may still free up
    finally:
        sock.close()


def check_no_hardcoded_secrets() -> bool:
    """Scan project files for likely hardcoded secret VALUES.

    Only flags real-looking values; never prints the value itself.
    """
    ok = True
    scan_exts = {".py", ".json", ".md", ".txt", ".env", ".yml", ".yaml"}
    for root, _dirs, files in os.walk(PROJECT_ROOT):
        rel_root = Path(root).relative_to(PROJECT_ROOT)
        # Skip directories that legitimately contain secrets or are heavy.
        skip_dirs = {".venv", "venv", "env", "__pycache__", "node_modules",
                     "data", "logs", "temp", ".git", ".trae", "handoff"}
        if any(part in skip_dirs for part in rel_root.parts):
            continue
        for fname in files:
            ext = Path(fname).suffix.lower()
            rel_path = str(rel_root / fname).replace("\\", "/")
            if ext not in scan_exts and not fname.endswith(".env.example"):
                continue
            if rel_path in SECRET_SCAN_ALLOWLIST:
                continue
            fpath = PROJECT_ROOT / rel_path
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                # Look for assignment of a real-looking secret value, e.g.
                # API_KEY="sk-xxxx" or ADMIN_BOOTSTRAP_TOKEN="AKIA..."
                for name in SECRET_NAME_PATTERNS:
                    if name not in line:
                        continue
                    # Detect quoted non-empty value following "=" or ":".
                    after = line.split(name, 1)[1] if name in line else ""
                    # Find first "=" or ":" after the name.
                    eq_idx = after.find("=")
                    col_idx = after.find(":")
                    cut = -1
                    for idx in (eq_idx, col_idx):
                        if idx >= 0 and (cut < 0 or idx < cut):
                            cut = idx
                    if cut < 0:
                        continue
                    value_part = after[cut + 1:].strip().strip(",").strip()
                    if not value_part:
                        continue
                    # Strip quotes.
                    if value_part[0] in "\"'":
                        value_part = value_part[1:].split(value_part[0], 1)[0]
                    if not value_part:
                        continue
                    # Heuristic: long, or starts with a known secret prefix,
                    # or all-uppercase placeholder is fine.
                    if value_part.isupper() and value_part.startswith("<"):
                        continue  # placeholder like <SET_LOCALLY>
                    if any(value_part.startswith(p) for p in SECRET_VALUE_HINTS):
                        _fail(f"Possible hardcoded secret in {rel_path}:{line_no} "
                              f"(variable {name}) — value redacted")
                        ok = False
                        break
                    if len(value_part) >= 24 and value_part.isalnum():
                        _fail(f"Possible hardcoded secret in {rel_path}:{line_no} "
                              f"(variable {name}) — value redacted")
                        ok = False
                        break
    if ok:
        _ok("No hardcoded secret values detected in tracked source/config files")
    return ok


def check_agent_protected() -> bool:
    """Ensure src/core/agent.py has not been modified from placeholder."""
    path = PROJECT_ROOT / "src" / "core" / "agent.py"
    if not path.is_file():
        _fail("src/core/agent.py missing — protected file must exist")
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"src/core/agent.py unreadable: {exc!r}")
        return False
    marker = "opportunity-analysis-core-placeholder"
    if marker in content and "def describe()" in content:
        _ok("src/core/agent.py is intact (placeholder, not modified)")
        return True
    _fail("src/core/agent.py appears modified — protected file must remain placeholder")
    return False


def main() -> int:
    print("=" * 72)
    print("Opportunity Analysis Tool — Local Environment Check")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python:       {sys.version}")
    print("=" * 72)

    results = []
    print("\n[1/11] Python version")
    results.append(check_python_version())

    print("\n[2/11] Optional dependency (openpyxl)")
    results.append(check_optional_dependency())

    print("\n[3/11] Backend package import")
    results.append(check_backend_importable())

    print("\n[4/11] Configuration files")
    results.append(check_config_files())

    print("\n[5/11] Dependency lock files")
    results.append(check_lock_files())

    print("\n[6/11] .env.example template")
    results.append(check_env_example())

    print("\n[7/11] Required directories")
    results.append(check_required_dirs())

    print("\n[8/11] SQLite path writable")
    results.append(check_writable_sqlite())

    print("\n[9/11] Web storage writable")
    results.append(check_writable_storage())

    print("\n[10/11] Output directory writable")
    results.append(check_writable_output())

    print("\n[11/11] Port availability (non-blocking)")
    # Port check is a warning; do not fail overall.
    check_port_available()

    print("\n[Extra] Hardcoded secret scan")
    results.append(check_no_hardcoded_secrets())

    print("\n[Extra] Protected file integrity (src/core/agent.py)")
    results.append(check_agent_protected())

    print("\n" + "=" * 72)
    if all(results):
        print("RESULT: PASS — environment is ready for development.")
        print("Next: copy .env.example to .env, fill in ADMIN_BOOTSTRAP_TOKEN, "
              "then run: python -m backend.app")
        return 0
    print(f"RESULT: FAIL — {sum(1 for r in results if not r)} check(s) failed. "
          "Fix the issues above before continuing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
