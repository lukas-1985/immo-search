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

Für den Dauerbetrieb startet die Aufgabenplanung den Server bei der Anmeldung und nach einem Absturz neu, siehe Abschnitt 7.

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

## 7. Unbeaufsichtigter Betrieb (Phase 6): Aufgabenplanung, Backup, Überwachung

### 7.1 Aufgaben anlegen (einmalig, macht der Nutzer)

Voraussetzungen: `claude auth login` ist erledigt, Docker Desktop startet mit Windows, automatische Anmeldung mit gesperrtem Bildschirm ist eingerichtet, Energiesparen und Ruhezustand sind aus (siehe PLAN.md, 11.2). Dann in einem normalen PowerShell-Fenster (ohne Admin):

```powershell
cd C:\E\ai-workspace\immo-search
powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1 -WasWaere   # nur anzeigen
powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1             # anlegen bzw. aktualisieren
```

Das Skript liest den Zeitplan aus `config/settings.yaml` (über `scripts/zeitplan.py`, also mit derselben Prüfung wie überall) und legt drei Aufgaben an:

| Aufgabe | Auslöser | Was passiert |
|---|---|---|
| `immo-search lauf` | täglich ab `schedule.run.from` alle `every_hours` Stunden bis `to` (Standard: 07, 10, 13, 16, 19, 22 Uhr) | `scripts/lauf.py` legt einen Job „lauf“ (ausgelöst von `zeitplan`) an und führt `run.ps1` aus: Sync → Regeln → Claude → Bewertung → Health. Er erscheint in der Oberfläche unter „Läufe“ mit Log. |
| `immo-search backup` | täglich um `schedule.backup.at` (Standard 03:00) | `scripts/backup.py` |
| `immo-search server` | bei Anmeldung, 1 min verzögert | `scripts/serve.py`. Stürzt er ab, startet `scripts/aufgabe.ps1` ihn nach 30 s neu (nach 5 schnellen Abstürzen in Folge erst nach 5 min). Stirbt auch die Schleife, startet die Aufgabenplanung sie neu. |

Gemeinsam: Sie laufen nur im angemeldeten Konto (wie Docker Desktop), mit normalen Rechten und verstecktem Fenster. Verpasste Termine werden nachgeholt, doppelte Starts verworfen. Läufe dürfen höchstens 2 h dauern (`run.ps1` begrenzt Claude zusätzlich auf 30 min, der Job auf 60 min). Ein Lauf aus der Oberfläche und ein zeitgesteuerter Lauf überschneiden sich nicht (Sperrdatei `data/run.lock`).

Nach einer Änderung von `schedule` in `settings.yaml` das Skript erneut ausführen. Entfernen: `… install_tasks.ps1 -Entfernen`.

Testen und bedienen:

```powershell
Start-ScheduledTask -TaskName 'immo-search server'   # sonst erst bei der nächsten Anmeldung
Start-ScheduledTask -TaskName 'immo-search backup'
Get-ScheduledTask -TaskName 'immo-search*' | Get-ScheduledTaskInfo | Format-Table TaskName, LastRunTime, LastTaskResult, NextRunTime
Stop-ScheduledTask -TaskName 'immo-search server'    # Server anhalten (z. B. vor git pull)
```

Logs: `data/logs/aufgabe-<lauf|backup|server>-JJJJMM.log`, jeder Lauf zusätzlich `data/logs/job-<id>.log`. Läuft nach `Stop-ScheduledTask` noch ein Python-Prozess auf Port 8710, ihn im Task-Manager beenden.

### 7.2 Backup

`uv run python scripts/backup.py` legt `<backup.ziel>/immo-JJJJMMTT-HHMMSS/` an:

- `immo.db`: Online-Backup über die SQLite-Backup-API, konsistent auch während eines Laufs, danach `integrity_check`
- `config/`: Kopie samt `.history/`
- `fredy/`: Fredys DB-Ordner (`backup.fredy_db_dir`). Fredys Dateien werden nie geöffnet, nur kopiert: DB und `-wal` roh in einen Zwischenordner, dort geprüft und zu einer Datei verdichtet. Bei einem inkonsistenten Schnappschuss (Fredy schreibt gerade) bis zu 3 Versuche.

Ein Backup heißt erst nach dem letzten Schritt so, vorher `….unvollstaendig`. Danach werden Backups älter als `aufbewahrung_tage` (14) gelöscht, die `mindestens_behalten` (3) neuesten bleiben immer. Ergebnis in `run_log` (Schritt `backup`); Exit-Code 2, wenn z. B. Fredys Ordner fehlt.

**Ziel:** Standard ist `data/backup`, also derselbe Datenträger (der Mini-PC hat nur C:). Gegen einen Plattendefekt hilft das nicht. Besser einen Ordner eintragen, der weg synchronisiert wird (NAS-Freigabe oder OneDrive), z. B. `ziel: "C:/Users/<name>/OneDrive/immo-backup"`.

**Wiederherstellen:** Server-Aufgabe anhalten, keinen Lauf starten, dann `immo.db` aus dem Backup nach `data/immo.db` kopieren (`data/immo.db-wal` und `-shm` vorher löschen) und `config/` zurückkopieren. Für Fredy: Container anhalten (`docker compose stop` im Fredy-Ordner), `listings.db` nach `C:\E\docker\fredy\db` kopieren, `-wal`/`-shm` dort löschen, Container starten.

### 7.3 Überwachung (Health)

`run.ps1` ruft am Ende jedes normalen Laufs `scripts/health.py` auf. Von Hand: `uv run python scripts/health.py [--ohne-server] [--streng]`. Geprüft wird (Grenzwerte in `settings.yaml` → `health`):

| Prüfung | ok, wenn … |
|---|---|
| `portal:<id>` | jedes Portal aus `health.portale` hat in den letzten `max_tage_ohne_angebot` (3) Tagen mindestens 1 neues Angebot geliefert |
| `sync` | der letzte fehlerfreie Sync ist höchstens `max_stunden_ohne_sync` (12) h alt; ein Fehler im letzten Versuch wird mit angezeigt |
| `backup` | das letzte fehlerfreie Backup ist höchstens `max_stunden_ohne_backup` (36) h alt |
| `server` | `GET /health` des Servers antwortet mit `ok` |

Das Ergebnis steht in `run_log` (Schritt `health`, Probleme in der Spalte `fehler`) und damit in der Oberfläche unter „Läufe“. Ein Problem macht den Lauf **nicht** zum Teilfehler. Bis Phase 5 wird nur protokolliert, danach kommt ein Telegram-Alarm dazu. Bekannt (19.10.2026): `portal:immowelt` schlägt fehl, solange Fredy dort vom Bot-Schutz blockiert wird.
