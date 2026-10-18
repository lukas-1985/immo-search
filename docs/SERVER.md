# immo-server (Phasen 7 und 8): Oberfläche, MCP, Läufe

Ein Prozess (`scripts/serve.py`, FastAPI + Uvicorn, Port 8710) stellt bereit:

- **Weboberfläche**: Übersicht, Angebotsliste mit Filtern, Detailansicht (Kaufpreisempfehlung mit Rechenweg, Score-Aufschlüsselung, Merkmale mit Belegstellen, Preisverlauf), Status und Notizen, Ranking-Simulation, Konfigurations-Editor, Läufe
- **MCP** unter `/mcp` (Streamable HTTP, Bearer-Token) für Claude Code / Claude Desktop
- **Job-Runner**: startet `run.ps1` (Sync → Regeln → Claude-Extraktion → Bewertung), ein Lauf gleichzeitig

Er arbeitet nur auf `data/immo.db` und `config/` und spricht nie direkt mit Fredy.

## 1. Einmalig einrichten (auf dem Mini-PC)

```powershell
cd C:\E\ai-workspace\immo-search
uv sync
uv run python scripts/set_password.py --mcp-token
```

`set_password.py` fragt das Passwort der Oberfläche verdeckt ab (mind. 10 Zeichen) und schreibt nur den Argon2-Hash nach `.env`. Dazu kommen `SESSION_SECRET` und mit `--mcp-token` ein neues `MCP_TOKEN`, das einmal angezeigt wird.

**Claude Code für unbeaufsichtigte Läufe anmelden** (einmalig, im Terminal):

```powershell
claude auth login
```

Prüfen: `claude auth status` muss `"loggedIn": true` zeigen. Ohne Anmeldung laufen Sync und Bewertung trotzdem, nur die Claude-Extraktion entfällt (Lauf endet mit „Teilfehler“).

## 2. Starten

```powershell
uv run python scripts/serve.py
```

Dann http://localhost:8710 öffnen. Der Server lauscht auf allen Adressen aus `config/settings.yaml` → `server.bind`. Adressen, die es (noch) nicht gibt, werden übersprungen.

Autostart „bei Anmeldung“ über die Aufgabenplanung folgt mit Phase 6.

## 3. Zugriff im Heimnetz und unterwegs (Tailscale)

1. Tailscale auf Mini-PC, Handy und Laptop installieren und anmelden (`winget install -e --id tailscale.tailscale`).
2. Die Tailscale-IP des Mini-PCs (`tailscale ip -4`, z. B. `100.x.y.z`) und bei Bedarf die LAN-IP in `config/settings.yaml` eintragen:
   ```yaml
   server:
     bind: ["127.0.0.1", "192.168.x.y", "100.x.y.z"]
     public_base_url: "http://immo-minipc:8710"   # MagicDNS-Name; wird für Links in MCP-Antworten benutzt
   ```
3. Server neu starten. Keine Portfreigabe im Router.
4. Windows-Firewall: Beim ersten Start fragt Windows nach. Zugriff nur für „Private Netzwerke“ erlauben.

## 4. MCP in Claude einbinden

**Claude Code** (auf dem Mini-PC oder einem Rechner im Tailnet):

```bash
claude mcp add --transport http immo http://immo-minipc:8710/mcp --header "Authorization: Bearer <MCP_TOKEN>"
```

**Claude Desktop**: Remote-Connectors laufen über die Cloud und erreichen das Heimnetz nicht. Deshalb eine lokale Brücke in `claude_desktop_config.json` eintragen:

```json
{ "mcpServers": { "immo": { "command": "npx", "args": ["-y", "mcp-remote", "http://immo-minipc:8710/mcp",
  "--header", "Authorization: Bearer <MCP_TOKEN>", "--allow-http"] } } }
```

(Die Optionen von `mcp-remote` sind noch nicht am echten System geprüft. Braucht Node.js. Getestet ist bisher der direkte HTTP-Zugang, wie ihn Claude Code nutzt.)

Werkzeuge:

| Lesen | Schreiben (einzeln in `server.mcp.write_tools` freischaltbar) |
|---|---|
| `list_profiles`, `search_listings`, `get_top_listings`, `get_listing`, `explain_score`, `compare_listings`, `get_changes`, `get_stats`, `simulate_scoring` (ohne Speichern), `get_jobs`, Ressource `immo://felder` | `set_status`, `add_note`, `start_run`, `reextract_listing` |

Nicht über MCP: Konfiguration ändern, Merkmale überschreiben, Daten löschen. `send_digest_now` kommt mit Phase 5, `simulate_listing`/`get_scenarios` mit Phase 8b.

## 5. Sicherheit

- Oberfläche: ein Benutzer, Passwort als Argon2-Hash, Sitzungs-Cookie (HttpOnly, SameSite=strict), CSRF-Token in allen Formularen.
- MCP: eigenes Bearer-Token, unabhängig vom Login.
- Job-Runner: nur feste Befehle (`run.ps1`, `score.py`), Profil-IDs und Angebots-IDs werden geprüft, Zeitlimit, Sperrdatei `data/run.lock`.
- Unbeaufsichtigter Claude-Lauf: `--permission-mode dontAsk` mit `.claude/run-settings.json`. Erlaubt sind nur Lesen im Projekt, `pending.py`/`save.py` und Schreiben unter `data/extraction/`, `.env` ist gesperrt. Alles andere wird automatisch abgelehnt.
- Konfigurations-Editor: schreibt nur `config/settings.yaml` und `config/profiles/*.yaml`, prüft vorher die komplette Konfiguration, legt immer ein Backup in `config/.history/` an und protokolliert in `config_change`. Danach werden alle Scores neu berechnet.

## 6. Läufe von Hand

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1                 # alle aktiven Profile
powershell -ExecutionPolicy Bypass -File run.ps1 -Profil mfh-kl
powershell -ExecutionPolicy Bypass -File run.ps1 -Listing 42 -Reextract
```

Exit-Codes: 0 ok, 1 Fehler (Sync/Regeln/Bewertung), 2 Teilfehler (z. B. Claude nicht angemeldet), 3 anderer Lauf aktiv. Logs: `data/logs/`.
