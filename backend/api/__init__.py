"""API routing framework built on Python's standard library.

Provides a lightweight Request/Response abstraction and a Router so
endpoint handlers can be written without touching http.server internals.
Production veFaaS handler translates its event format into the same
Request objects.
"""
from __future__ import annotations

import json
import mimetypes
import re
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------


@dataclass
class Request:
    method: str
    path: str
    query_params: Dict[str, List[str]] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    path_params: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    current_user: Optional[str] = None

    @property
    def json(self) -> Any:
        if not self.body:
            return {}
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def query(self, name: str, default: str = "") -> str:
        values = self.query_params.get(name)
        return values[0] if values else default


@dataclass
class Response:
    status: int = HTTPStatus.OK
    body: bytes = b""
    headers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, data: Any, status: int = HTTPStatus.OK) -> "Response":
        payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        return cls(
            status=status,
            body=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    @classmethod
    def text(cls, text: str, status: int = HTTPStatus.OK) -> "Response":
        return cls(
            status=status,
            body=text.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )

    @classmethod
    def file(cls, data: bytes, filename: str, content_type: str = "") -> "Response":
        if not content_type:
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return cls(
            status=HTTPStatus.OK,
            body=data,
            headers={
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @classmethod
    def error(cls, status: int, message: str) -> "Response":
        return cls.json({"error": message}, status=status)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

Handler = Callable[[Request], Response]


@dataclass
class _Route:
    method: str
    pattern: re.Pattern
    param_names: List[str]
    handler: Handler


class Router:
    """Simple regex-based router."""

    def __init__(self) -> None:
        self._routes: List[_Route] = []

    def _register(self, method: str, path: str, handler: Handler) -> None:
        param_names: List[str] = []
        regex_parts: List[str] = []
        for segment in path.split("/"):
            if not segment:
                continue
            if segment.startswith("{") and segment.endswith("}"):
                name = segment[1:-1]
                param_names.append(name)
                regex_parts.append(r"(?P<%s>[^/]+)" % name)
            else:
                regex_parts.append(re.escape(segment))
        pattern = re.compile(r"^/" + "/".join(regex_parts) + r"/?$")
        self._routes.append(_Route(method, pattern, param_names, handler))

    def get(self, path: str) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self._register("GET", path, handler)
            return handler
        return decorator

    def post(self, path: str) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self._register("POST", path, handler)
            return handler
        return decorator

    def put(self, path: str) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self._register("PUT", path, handler)
            return handler
        return decorator

    def delete(self, path: str) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self._register("DELETE", path, handler)
            return handler
        return decorator

    def match(self, method: str, path: str) -> Optional[Tuple[Handler, Dict[str, str]]]:
        for route in self._routes:
            if route.method != method:
                continue
            match = route.pattern.match(path)
            if match:
                return route.handler, match.groupdict()
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_cookie_header(header: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in header.split(";"):
        part = part.strip()
        if "=" in part:
            name, value = part.split("=", 1)
            cookies[name.strip()] = value.strip()
    return cookies


def build_request(method: str, raw_path: str, headers: Dict[str, str], body: bytes) -> Request:
    parsed = urlparse(raw_path)
    query_params: Dict[str, List[str]] = {
        k: v for k, v in parse_qs(parsed.query).items()
    }
    # Normalize header keys to lowercase so lookups are case-insensitive.
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    cookie_header = normalized_headers.get("cookie", "")
    cookies = parse_cookie_header(cookie_header)
    return Request(
        method=method,
        path=parsed.path,
        query_params=query_params,
        headers=normalized_headers,
        body=body,
        cookies=cookies,
    )
