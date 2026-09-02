"""Transparent anonymous sessions for the zero-configuration public build.

The browser receives a signed, HttpOnly cookie automatically. The identifier
isolates projects and applies modest per-session quotas; it is not an account
and contains no personal information. The signing secret lives only in the
cloud environment.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from fastapi import Request, Response

from app.config import Settings


COOKIE_NAME = "scivis_session"


@dataclass(frozen=True)
class AnonymousSession:
    session_id: str
    is_new: bool


def _signature(session_id: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), session_id.encode("ascii"), hashlib.sha256).hexdigest()


def encode_session(session_id: str, secret: str) -> str:
    return f"{session_id}.{_signature(session_id, secret)}"


def decode_session(value: str, secret: str) -> str | None:
    try:
        session_id, supplied = value.split(".", 1)
    except ValueError:
        return None
    if len(session_id) != 32 or any(ch not in "0123456789abcdef" for ch in session_id):
        return None
    return session_id if hmac.compare_digest(supplied, _signature(session_id, secret)) else None


def session_for(request: Request, settings: Settings) -> AnonymousSession:
    if not settings.public_access_enabled:
        return AnonymousSession("local", False)
    existing = decode_session(request.cookies.get(COOKIE_NAME, ""), settings.public_session_secret)
    if existing:
        return AnonymousSession(existing, False)
    return AnonymousSession(secrets.token_hex(16), True)


def attach_cookie(response: Response, session: AnonymousSession, settings: Settings) -> None:
    if not settings.public_access_enabled or not session.is_new:
        return
    response.set_cookie(
        COOKIE_NAME,
        encode_session(session.session_id, settings.public_session_secret),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )


def owner_from(request: Request) -> str:
    return getattr(request.state, "scivis_session_id", "local")
