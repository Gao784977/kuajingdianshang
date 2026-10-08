"""Authentication service: invitation codes, sessions, CSRF.

Design notes:
- ``ADMIN_BOOTSTRAP_TOKEN`` is **only** used to bootstrap an admin user
  or to create invitation records. It is NOT a shared login credential
  for all users.
- Each friend authenticates with an independent invitation code that
  creates an independent ``user_id``.
- Invitation codes are stored as SHA-256 hashes only (never plaintext).
- Sessions are HttpOnly cookies with explicit expiration.
- Login failures are rate-limited per client IP.
- State-changing endpoints require CSRF token validation (or Origin
  check when CSRF token is absent).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
import uuid
from typing import Dict, List, Optional, Tuple

from backend.config import (
    LOGIN_RATE_LIMIT_PER_MIN,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SESSION_TTL_SECONDS,
)
from backend.storage.database import get_job_store


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def hash_token(token: str) -> str:
    """SHA-256 hash of a token. Stored in DB instead of plaintext."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    """Generate a random URL-safe invitation token."""
    return secrets.token_urlsafe(24)


def generate_session_id() -> str:
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per-IP)
# ---------------------------------------------------------------------------

class _RateLimiter:
    def __init__(self, limit_per_min: int) -> None:
        self._limit = limit_per_min
        self._attempts: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            attempts = [t for t in self._attempts.get(key, []) if now - t < 60]
            self._attempts[key] = attempts
            if len(attempts) >= self._limit:
                return False
            attempts.append(now)
            return True


_rate_limiter = _RateLimiter(LOGIN_RATE_LIMIT_PER_MIN)


# ---------------------------------------------------------------------------
# AuthService
# ---------------------------------------------------------------------------

class AuthService:
    """Manages invitations, users, sessions, and CSRF tokens."""

    def __init__(self) -> None:
        self._store = get_job_store()
        # CSRF token per session_id
        self._csrf_tokens: Dict[str, str] = {}

    # -- invitations -------------------------------------------------------

    def create_invitation(
        self,
        max_uses: int = 1,
        expires_at: Optional[float] = None,
    ) -> Tuple[str, str]:
        """Create a new invitation. Returns (invitation_id, plaintext_token)."""
        invitation_id = str(uuid.uuid4())
        plaintext = generate_invite_token()
        token_hash = hash_token(plaintext)
        self._store._execute(
            """
            INSERT INTO invitations (invitation_id, token_hash, max_uses, expires_at, status, created_at)
            VALUES (?, ?, ?, ?, 'active', ?)
            """,
            (invitation_id, token_hash, max_uses, expires_at, time.time()),
        )
        return invitation_id, plaintext

    def _find_invitation(self, plaintext_token: str) -> Optional[Dict]:
        token_hash = hash_token(plaintext_token)
        row = self._store._query_one(
            "SELECT * FROM invitations WHERE token_hash = ?", (token_hash,)
        )
        return dict(row) if row else None

    # -- users -------------------------------------------------------------

    def _get_or_create_user(self, username: str) -> str:
        row = self._store._query_one(
            "SELECT user_id FROM users WHERE username = ?", (username,)
        )
        if row:
            return row["user_id"]
        user_id = str(uuid.uuid4())
        self._store._execute(
            "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
            (user_id, username, time.time()),
        )
        return user_id

    # -- login -------------------------------------------------------------

    def login(
        self, token: str, client_ip: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Authenticate with an invitation token.

        Returns ``(session_id, user_id, csrf_token)`` or
        ``(None, None, None)`` on failure.
        """
        # Rate limit by IP
        if not _rate_limiter.is_allowed(client_ip):
            return None, None, None

        invitation = self._find_invitation(token)
        if invitation is None:
            # Fall back to admin bootstrap token (temporary admin login).
            # Read from os.environ at call time so tests can set it in setUp.
            admin_token = os.environ.get("ADMIN_BOOTSTRAP_TOKEN", "")
            if admin_token and hmac.compare_digest(token, admin_token):
                user_id = self._get_or_create_user("admin")
            else:
                return None, None, None
        else:
            # Validate invitation
            if invitation["status"] != "active":
                return None, None, None
            if invitation["expires_at"] and invitation["expires_at"] < time.time():
                return None, None, None
            if invitation["used_count"] >= invitation["max_uses"]:
                return None, None, None
            # Mark as used
            self._store._execute(
                "UPDATE invitations SET used_count = used_count + 1 WHERE invitation_id = ?",
                (invitation["invitation_id"],),
            )
            username = f"invitee_{invitation['invitation_id'][:8]}"
            user_id = self._get_or_create_user(username)

        # Create session
        session_id = generate_session_id()
        csrf_token = generate_csrf_token()
        now = time.time()
        self._store._execute(
            """
            INSERT INTO sessions (session_id, user_id, created_at, expires_at, revoked)
            VALUES (?, ?, ?, ?, 0)
            """,
            (session_id, user_id, now, now + SESSION_TTL_SECONDS),
        )
        self._csrf_tokens[session_id] = csrf_token
        return session_id, user_id, csrf_token

    # -- session validation ------------------------------------------------

    def get_session(self, session_id: str) -> Optional[Dict]:
        row = self._store._query_one(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        )
        if not row:
            return None
        data = dict(row)
        if data["revoked"]:
            return None
        if data["expires_at"] < time.time():
            return None
        return data

    def get_user_id_from_session(self, session_id: str) -> Optional[str]:
        session = self.get_session(session_id)
        return session["user_id"] if session else None

    def get_csrf_token(self, session_id: str) -> str:
        token = self._csrf_tokens.get(session_id)
        if not token:
            token = generate_csrf_token()
            self._csrf_tokens[session_id] = token
        return token

    def validate_csrf(self, session_id: str, token: Optional[str]) -> bool:
        if not token:
            return False
        expected = self._csrf_tokens.get(session_id)
        if not expected:
            return False
        return hmac.compare_digest(token, expected)

    def logout(self, session_id: str) -> None:
        self._store._execute(
            "UPDATE sessions SET revoked = 1 WHERE session_id = ?", (session_id,)
        )
        self._csrf_tokens.pop(session_id, None)

    # -- cookie helpers ----------------------------------------------------

    def build_session_cookie(self, session_id: str) -> str:
        parts = [
            f"{SESSION_COOKIE_NAME}={session_id}",
            "Path=/",
            "HttpOnly",
            f"SameSite={SESSION_COOKIE_SAMESITE}",
        ]
        if SESSION_COOKIE_SECURE:
            parts.append("Secure")
        return "; ".join(parts)

    def clear_session_cookie(self) -> str:
        parts = [
            f"{SESSION_COOKIE_NAME}=",
            "Path=/",
            "HttpOnly",
            "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
        ]
        return "; ".join(parts)


# Module-level singleton
_auth_service: Optional[AuthService] = None
_auth_lock = threading.Lock()


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        with _auth_lock:
            if _auth_service is None:
                _auth_service = AuthService()
    return _auth_service
