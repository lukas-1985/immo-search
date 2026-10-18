"""immo-server starten (Oberfläche + MCP + Job-Runner).

    python scripts/serve.py [--config-dir config] [--db data/immo.db] [--port 8710] [--host 127.0.0.1 ...]

Lauscht auf allen Adressen aus settings.yaml → server.bind (localhost, LAN, Tailscale). Adressen, die es
(noch) nicht gibt – z. B. Tailscale vor der Anmeldung –, werden mit einer Warnung übersprungen.
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys

import uvicorn

from immo.config import load_config
from immo.server import create_app


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config-dir")
    ap.add_argument("--db")
    ap.add_argument("--port", type=int)
    ap.add_argument("--host", action="append", help="statt server.bind (mehrfach möglich)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config_dir)
    port = args.port or cfg.settings.server.port
    hosts = args.host or cfg.settings.server.bind

    sockets = []
    for host in hosts:
        fam = socket.AF_INET6 if ":" in host else socket.AF_INET
        s = socket.socket(fam, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
        except OSError as exc:
            logging.warning("Adresse %s:%s nicht verfügbar (%s) – übersprungen", host, port, exc)
            s.close()
            continue
        s.set_inheritable(True)
        sockets.append(s)
        logging.info("immo-server lauscht auf http://%s:%s", host if fam == socket.AF_INET else f"[{host}]", port)
    if not sockets:
        logging.error("Keine Adresse verfügbar – Abbruch")
        return 1

    app = create_app(args.config_dir, args.db)
    server = uvicorn.Server(uvicorn.Config(app, log_level="info", proxy_headers=False, access_log=False))
    server.run(sockets=sockets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
