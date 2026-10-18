"""Anmeldung der Oberfläche (ein Benutzer, Argon2-Hash in .env), CSRF-Schutz und MCP-Bearer-Token."""

from __future__ import annotations

import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request
from starlette.types import ASGIApp, Receive, Scope, Send

_HASHER = PasswordHasher()


def hash_passwort(passwort: str) -> str:
    return _HASHER.hash(passwort)


def passwort_ok(passwort: str, passwort_hash: str | None) -> bool:
    if not passwort_hash or not passwort:
        return False
    try:
        return _HASHER.verify(passwort_hash, passwort)
    except (VerificationError, InvalidHashError):
        return False


def angemeldet(request: Request) -> bool:
    return request.session.get("angemeldet") is True


def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        request.session["csrf"] = tok
    return tok


def pruefe_csrf(request: Request, gesendet: str | None) -> None:
    erwartet = request.session.get("csrf")
    if not erwartet or not gesendet or not hmac.compare_digest(erwartet, gesendet):
        raise HTTPException(status_code=403, detail="CSRF-Prüfung fehlgeschlagen – Seite neu laden")


class BearerSchutz:
    """ASGI-Hülle um die MCP-App: nur Pfade unter /mcp, nur mit gültigem Bearer-Token."""

    def __init__(self, app: ASGIApp, token: str | None):
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http" or not scope["path"].startswith("/mcp"):
            await _antwort(send, 404, b"Nicht gefunden")
            return
        if not self.token:
            await _antwort(send, 503, b"MCP_TOKEN ist nicht gesetzt (.env)")
            return
        header = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
        if not header.startswith("Bearer ") or not hmac.compare_digest(header[7:], self.token):
            await _antwort(send, 401, b"Bearer-Token fehlt oder ist falsch", [(b"www-authenticate", b"Bearer")])
            return
        await self.app(scope, receive, send)


async def _antwort(send: Send, status: int, text: bytes, extra: list[tuple[bytes, bytes]] | None = None) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"), *(extra or [])]})
    await send({"type": "http.response.body", "body": text})
