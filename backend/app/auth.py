from __future__ import annotations

import base64
import secrets
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings


class OptionalBasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.auth_enabled or _is_exempt_path(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if _valid_basic_auth(auth_header):
            return await call_next(request)

        return Response(
            "Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="SoundTouch Local"'},
        )


def _is_exempt_path(path: str) -> bool:
    return path.startswith("/stream/") or path.startswith("/bose/") or path == "/api/health"


def _valid_basic_auth(header: str) -> bool:
    prefix = "Basic "
    if not header.startswith(prefix):
        return False
    try:
        decoded = base64.b64decode(header[len(prefix) :]).decode("utf-8")
    except Exception:
        return False
    username, separator, password = decoded.partition(":")
    if not separator:
        return False
    return secrets.compare_digest(username, settings.auth_username) and secrets.compare_digest(
        password, settings.auth_password
    )
