from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import bcrypt
from fastapi import Request
from fastapi.responses import RedirectResponse


AUTH_COOKIE_MAX_AGE_SECONDS = 90 * 24 * 60 * 60
AUTH_COOKIE_NAME = "command_center_auth"


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    password_hash: str
    secret: str
    secure_cookie: bool


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_auth_token(secret: str, now: int | None = None) -> str:
    issued_at = int(now if now is not None else time.time())
    payload = _encode_json({"iat": issued_at})
    signature = _sign(secret, payload)
    return f"{payload}.{signature}"


def is_valid_auth_token(token: str | None, secret: str, now: int | None = None) -> bool:
    if not token or not secret:
        return False
    try:
        payload, signature = token.split(".", 1)
    except ValueError:
        return False

    expected_signature = _sign(secret, payload)
    if not hmac.compare_digest(signature, expected_signature):
        return False

    try:
        data = json.loads(_decode_base64(payload))
        issued_at = int(data["iat"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False

    current_time = int(now if now is not None else time.time())
    if issued_at > current_time + 60:
        return False
    return current_time - issued_at <= AUTH_COOKIE_MAX_AGE_SECONDS


def login_redirect(request: Request) -> RedirectResponse:
    query = urlencode({"next": _safe_next_path(request)})
    return RedirectResponse(f"/login?{query}", status_code=303)


def set_auth_cookie(response: RedirectResponse, token: str, secure: bool) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=AUTH_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def clear_auth_cookie(response: RedirectResponse, secure: bool) -> None:
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def normalize_next_path(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def _safe_next_path(request: Request) -> str:
    path = request.url.path or "/"
    if request.url.query:
        return f"{path}?{request.url.query}"
    return path


def _sign(secret: str, payload: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _encode_base64(digest)


def _encode_json(data: dict[str, int]) -> str:
    return _encode_base64(json.dumps(data, separators=(",", ":")).encode("utf-8"))


def _encode_base64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_base64(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}").decode("utf-8")
