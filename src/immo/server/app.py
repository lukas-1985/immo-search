"""immo-server: Oberfläche, MCP und Job-Runner in einem Prozess (FastAPI + Uvicorn).

Arbeitet nur auf data/immo.db und config/; spricht nie direkt mit Fredy.
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.sessions import SessionMiddleware

from ..config import Config, load_config, secret
from ..db import connect
from ..jobs import Runner
from .auth import BearerSchutz

log = logging.getLogger("immo.server")


class Zustand:
    """Gemeinsamer Zustand: Konfiguration (wird nach Änderungen neu geladen) und DB-Pfad."""

    def __init__(self, config_dir: Path | None, db_path: Path | None):
        self.config_dir = config_dir
        self.config: Config = load_config(config_dir)
        self.db_path = db_path or self.config.db_path()

    def neu_laden(self) -> Config:
        self.config = load_config(self.config.config_dir)
        return self.config

    def db(self) -> sqlite3.Connection:
        return connect(self.db_path, check_same_thread=False)

    def verbindung(self) -> Iterator[sqlite3.Connection]:
        conn = self.db()
        try:
            yield conn
        finally:
            conn.close()


def create_app(config_dir: Path | str | None = None, db_path: Path | str | None = None, *, runner: bool = True) -> FastAPI:
    zustand = Zustand(Path(config_dir) if config_dir else None, Path(db_path) if db_path else None)
    cfg = zustand.config

    from .mcp_tools import baue_mcp
    from .web import router

    mcp = baue_mcp(zustand) if cfg.settings.server.mcp.enabled else None
    # DNS-Rebinding-Schutz des SDK erlaubt nur localhost als Host; Zugriff kommt aber auch über LAN/Tailscale-Namen.
    # Schutz bietet hier das Bearer-Token (ein Browser auf einer fremden Seite kennt es nicht).
    sicherheit = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    mcp_app = (mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                       transport_security=sicherheit) if mcp else None)
    job_runner = Runner(zustand.config, zustand.db_path) if runner else None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if job_runner:
            job_runner.start()
        if mcp:
            async with mcp.session_manager.run():
                yield
        else:
            yield
        if job_runner:
            job_runner.stop()

    app = FastAPI(title="immo-search", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.zustand = zustand
    sitzung = secret("SESSION_SECRET")
    if not sitzung:
        log.warning("SESSION_SECRET fehlt in .env – Anmeldungen gelten nur bis zum Neustart (scripts/set_password.py)")
        sitzung = secrets.token_urlsafe(32)
    app.add_middleware(SessionMiddleware, secret_key=sitzung, session_cookie="immo_session", same_site="strict",
                       https_only=False, max_age=14 * 24 * 3600)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
    if mcp_app is not None:
        app.mount("/", BearerSchutz(mcp_app, secret("MCP_TOKEN")))
    return app
