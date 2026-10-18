"""Zugangsdaten des immo-servers in .env schreiben (Passwort wird verdeckt abgefragt, nur der Hash landet in .env).

    python scripts/set_password.py              # Passwort der Oberfläche setzen
    python scripts/set_password.py --mcp-token   # zusätzlich ein neues MCP-Token erzeugen und anzeigen

Legt außerdem SESSION_SECRET an, falls es fehlt. Danach den Server neu starten.
"""

from __future__ import annotations

import argparse
import getpass
import re
import secrets
import sys
from pathlib import Path

from immo.server.auth import hash_passwort

ENV = Path(__file__).resolve().parent.parent / ".env"


def setze(text: str, name: str, wert: str) -> str:
    zeile = f"{name}={wert}"
    if re.search(rf"^{name}=.*$", text, flags=re.M):
        return re.sub(rf"^{name}=.*$", lambda _: zeile, text, flags=re.M)
    return text.rstrip("\n") + f"\n{zeile}\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mcp-token", action="store_true", help="neues MCP-Token erzeugen")
    ap.add_argument("--nur-token", action="store_true", help="Passwort nicht ändern, nur Token/Session-Secret")
    args = ap.parse_args()

    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    if not args.nur_token:
        pw = getpass.getpass("Neues Passwort für die Oberfläche: ")
        if len(pw) < 10:
            print("Bitte mindestens 10 Zeichen.", file=sys.stderr)
            return 1
        if pw != getpass.getpass("Wiederholen: "):
            print("Die Eingaben stimmen nicht überein.", file=sys.stderr)
            return 1
        text = setze(text, "UI_PASSWORD_HASH", hash_passwort(pw))
        print("UI_PASSWORD_HASH gesetzt.")
    if not re.search(r"^SESSION_SECRET=\S+", text, flags=re.M):
        text = setze(text, "SESSION_SECRET", secrets.token_urlsafe(48))
        print("SESSION_SECRET angelegt.")
    if args.mcp_token:
        token = secrets.token_urlsafe(32)
        text = setze(text, "MCP_TOKEN", token)
        print(f"MCP_TOKEN gesetzt: {token}")
        print("Einbinden in Claude Code:")
        print(f'  claude mcp add --transport http immo http://<host>:8710/mcp --header "Authorization: Bearer {token}"')
    ENV.write_text(text, encoding="utf-8")
    print(f"Gespeichert in {ENV}. Server neu starten.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
