"""Backend configuration loaded from environment variables.

All sensitive values (API keys, access keys, secret keys) come from
environment variables only. They are never written to code, frontend,
HTML, or README examples.
"""
from __future__ import annotations

import os
from typing import List

APP_VERSION = "v3.2"

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.environ.get(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Public configuration
# ---------------------------------------------------------------------------

APP_ENV = _env("APP_ENV", "local")
HOST = _env("HOST", "0.0.0.0")
PORT = _env_int("PORT", 8000)

# Authentication
ADMIN_BOOTSTRAP_TOKEN = _env("ADMIN_BOOTSTRAP_TOKEN", "")
SESSION_COOKIE_NAME = _env("SESSION_COOKIE_NAME", "session_id")
SESSION_TTL_SECONDS = _env_int("SESSION_TTL_SECONDS", 86400)  # 24h
LOGIN_RATE_LIMIT_PER_MIN = _env_int("LOGIN_RATE_LIMIT_PER_MIN", 10)

# Cookie security
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", APP_ENV == "production")
SESSION_COOKIE_SAMESITE = _env("SESSION_COOKIE_SAMESITE", "Lax")

# CORS
ALLOWED_ORIGINS = _env_list("ALLOWED_ORIGINS", [])

# File upload
MAX_UPLOAD_SIZE_MB = _env_int("MAX_UPLOAD_SIZE_MB", 50)
ALLOWED_UPLOAD_EXTENSIONS = {"xlsx", "csv", "json"}

# Storage
DATA_DIR = _env("DATA_DIR", "data")
WEB_STORAGE_DIR = os.path.join(DATA_DIR, "web_storage")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
SQLITE_PATH = os.path.join(DATA_DIR, "web.db")

# URL fetch security
URL_FETCH_ENABLED = _env_bool("URL_FETCH_ENABLED", False)
URL_FETCH_MAX_REDIRECTS = _env_int("URL_FETCH_MAX_REDIRECTS", 3)
URL_FETCH_MAX_BYTES = _env_int("URL_FETCH_MAX_BYTES", 5 * 1024 * 1024)  # 5 MB
URL_FETCH_CONNECT_TIMEOUT = _env_int("URL_FETCH_CONNECT_TIMEOUT", 5)
URL_FETCH_READ_TIMEOUT = _env_int("URL_FETCH_READ_TIMEOUT", 10)

# Mock data (demo/test only)
MOCK_DATA_ENABLED = _env_bool("MOCK_DATA_ENABLED", False)

# Workflow definition (single source of truth for frontend Agent rendering)
WORKFLOW_DEFINITION = {
    "workflow_version": APP_VERSION,
    "phases": [
        {
            "name": "phase_1_research",
            "agents": [
                "input_validation",
                "workbook_detection",
                "schema_mapping",
                "excel_import",
                "url_fetch",
                "keyword",
                "market",
                "competitor",
                "brand_seller",
                "review",
                "opportunity",
                "product_candidate",
            ],
        },
        {
            "name": "phase_2_development",
            "agents": [
                "product_development",
                "profit",
                "report",
                "excel",
            ],
        },
    ],
}
