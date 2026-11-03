# immo-server (Phasen 7 und 8): Oberfläche, MCP, Läufe

Ein Prozess (`scripts/serve.py`, FastAPI + Uvicorn, Port 8710) stellt bereit:

- **Weboberfläche**: Übersicht, Angebotsliste mit Filtern, Detailansicht (Kaufpreisempfehlung mit Rechenweg, Score-Aufschlüsselung, Merkmale mit Belegstellen, Preisverlauf), Status und Notizen, Ranking-Simulation, Konfigurations-Editor, Läufe
- **MCP** unter `/mcp` (Streamable HTTP, Bearer-Token) für Codex
- **Job-Runner**: startet `run.ps1` (Sync → Regeln → Codex-Extraktion → Bewertung), ein Lauf gleichzeitig

Er arbeitet nur auf `data/immo.db` und `config/` und spricht nie direkt mit Fredy.

## 1. Einmalig einrichten (auf dem Mini-PC)

```powershell
cd C:\E\ai-workspace\immo-search
uv sync
uv run python scripts/set_password.py --mcp-token
```

`set_password.py` fragt das Passwort der Oberfläche verdeckt ab (mind. 10 Zeichen) und schreibt nur den Argon2-Hash nach `.env`. Dazu kommen `SESSION_SECRET` und mit `--mcp-token` ein neues `MCP_TOKEN`, das einmal angezeigt wird.

**Codex für unbeaufsichtigte Läufe anmelden** (einmalig, im Terminal):

```powershell
codex login
```

Prüfen: `codex login status` muss eine ChatGPT-Anmeldung zeigen. Ohne Anmeldung laufen Sync und Bewertung trotzdem, nur die Codex-Extraktion entfällt (Lauf endet mit „Teilfehler“).

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

## 4. MCP in Codex einbinden

Auf dem Mini-PC oder einem Rechner im Tailnet, Token lokal als Umgebungsvariable `MCP_TOKEN` setzen:

```powershell
codex mcp add immo --url http://immo-minipc:8710/mcp --bearer-token-env-var MCP_TOKEN
```

Die Variable muss auch beim späteren Start von Codex verfügbar sein. Token nicht in Git speichern.
Die KI-Extraktion benötigt diese MCP-Verbindung nicht. ChatGPT Web benötigt einen von dort erreichbaren Server;
die lokale/Tailscale-Adresse allein stellt diesen Zugang nicht her.

Werkzeuge:

| Lesen | Schreiben (einzeln in `server.mcp.write_tools` freischaltbar) |
|---|---|
| `list_profiles`, `search_listings`, `get_top_listings`, `get_listing`, `explain_score`, `compare_listings`, `get_changes`, `get_stats`, `simulate_scoring` (ohne Speichern), `get_jobs`, Ressource `immo://felder` | `set_status`, `add_note`, `start_run`, `reextract_listing` |

Nicht über MCP: Konfiguration ändern, Merkmale überschreiben, Daten löschen. `send_digest_now` kommt mit Phase 5. Die Objekt-Simulation (Phase 8b) gibt es bewusst nur in der Oberfläche.

## 5. Sicherheit

- Oberfläche: ein Benutzer, Passwort als Argon2-Hash, Sitzungs-Cookie (HttpOnly, SameSite=strict), CSRF-Token in allen Formularen.
- MCP: eigenes Bearer-Token, unabhängig vom Login.
- Job-Runner: nur feste Befehle (`run.ps1`, `score.py`), Profil-IDs und Angebots-IDs werden geprüft, Zeitlimit, Sperrdatei `data/run.lock`.
- KI-Lauf: Python übergibt nur Vorlagen und Regeln an `codex exec`. Isolierter temporärer Arbeitsordner, read-only, Shell und Websuche deaktiviert, ohne Benutzerkonfiguration/MCP. Keine App-Geheimnisse in der Kindprozess-Umgebung. Die Speicherung erfolgt ausschließlich durch Python nach Prüfung.
- Konfigurations-Editor: schreibt nur `config/settings.yaml` und `config/profiles/*.yaml`, prüft vorher die komplette Konfiguration, legt immer ein Backup in `config/.history/` an und protokolliert in `config_change`. Danach werden alle Scores neu berechnet.

## 6. Läufe von Hand

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1                 # alle aktiven Profile
powershell -ExecutionPolicy Bypass -File run.ps1 -Profil mfh-kl
powershell -ExecutionPolicy Bypass -File run.ps1 -Listing 42 -Reextract
```

Exit-Codes: 0 ok, 1 Fehler (Sync/Regeln/Bewertung), 2 Teilfehler (z. B. Codex nicht angemeldet), 3 anderer Lauf aktiv. Logs: `data/logs/`.

## 7. Unbeaufsichtigter Betrieb (Phase 6): Aufgabenplanung, Backup, Überwachung

### 7.1 Aufgaben anlegen (einmalig, macht der Nutzer)

Voraussetzungen: `codex login` ist erledigt, Docker Desktop startet mit Windows, automatische Anmeldung mit gesperrtem Bildschirm ist eingerichtet, Energiesparen und Ruhezustand sind aus (siehe PLAN.md, 11.2). Dann in einem normalen PowerShell-Fenster (ohne Admin):

```powershell
cd C:\E\ai-workspace\immo-search
powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1 -WasWaere   # nur anzeigen
powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1             # anlegen bzw. aktualisieren
```

Das Skript liest den Zeitplan aus `config/settings.yaml` (über `scripts/zeitplan.py`, also mit derselben Prüfung wie überall) und legt drei Aufgaben an:

| Aufgabe | Auslöser | Was passiert |
|---|---|---|
| `immo-search lauf` | täglich ab `schedule.run.from` alle `every_hours` Stunden bis `to` (Standard: 07, 10, 13, 16, 19, 22 Uhr) | `scripts/lauf.py` legt einen Job „lauf“ (ausgelöst von `zeitplan`) an und führt `run.ps1` aus: Sync → Regeln → Codex → Bewertung → Health. Er erscheint in der Oberfläche unter „Läufe“ mit Log. |
| `immo-search backup` | täglich um `schedule.backup.at` (Standard 03:00) | `scripts/backup.py` |
| `immo-search server` | bei Anmeldung, 1 min verzögert | `scripts/serve.py`. Stürzt er ab, startet `scripts/aufgabe.ps1` ihn nach 30 s neu (nach 5 schnellen Abstürzen in Folge erst nach 5 min). Stirbt auch die Schleife, startet die Aufgabenplanung sie neu. |

Gemeinsam: Sie laufen nur im angemeldeten Konto (wie Docker Desktop), mit normalen Rechten und verstecktem Fenster. Verpasste Termine werden nachgeholt, doppelte Starts verworfen. Die Windows-Aufgabe hat ein Zeitlimit von 2 h. Der Job-Runner begrenzt vollständige Läufe auf 60 min und Neuauswertungen auf 30 min; `scripts/extract.py` begrenzt zusätzlich die gesamte KI-Extraktion über `ki.zeitlimit_s` (Standard 30 min). Ein Lauf aus der Oberfläche und ein zeitgesteuerter Lauf überschneiden sich nicht (Sperrdatei `data/run.lock`).

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

## 8. KI-Umstellung (03.11.2026)

Voraussetzung: Codex CLI mit `exec`, `--output-schema` und `--ignore-user-config`; Anmeldung im gleichen Windows-Konto wie Server und Aufgabenplanung. Geprüfte CLI: 0.166.0-alpha.5.1.
`ki.modell: null` nutzt den CLI-Standard ohne Benutzerkonfiguration. Ein konkreter Modellname pinnt die Auswahl.
Nutzungskontingente hängen vom ChatGPT-Konto ab. Kein automatischer Wechsel zu API-Abrechnung.
`ki.zeitlimit_s` begrenzt alle Stapel einschließlich Korrekturen zusammen; höchstens drei Stapel à 20 Angebote.
Ein eindeutig zuordenbares Ergebnis mit Format-, Feld-, Fachschema- oder Hash-Fehler erhält höchstens einen Korrekturversuch im selben Stapel. Gültige Ergebnisse werden vorher gespeichert und nicht erneut gesendet. Eine strukturell ungültige Antwort sowie fremde, doppelte oder fehlende Angebots-IDs bleiben ein Fehler des gesamten Stapels. Einzelne verworfene Felder führen zum Teilfehler,
aber nicht zu einer erneuten Auswertung des erfolgreich gespeicherten Angebots. Technische Ausfälle lassen offene Angebote offen.
Nach weiterhin abgelehntem Ergebnis wird kein weiterer Stapel verarbeitet. Die Auswahl für spätere Läufe berücksichtigt `MAX_VERSUCHE = 3`; ein unmittelbarer Korrekturversuch ist ein zusätzlicher Speicheraufruf.
Nicht behobene Formatfehler werden in `extraction_status` gezählt, ohne bestehende Feldwerte des betroffenen Angebots zu löschen. Rohantworten bleiben unter `data/extraction/codex-*.antwort.json` erhalten; normalisierte gültige Ergebnisse unter `codex-*.json`.
Auch Restangebote nach Erreichen der Stapelgrenze führen zu Exit 2. Nur neue/geänderte oder ausdrücklich angeforderte Angebote werden vorgelegt; Beschreibungen unter 40 Zeichen werden übersprungen, über 8 000 Zeichen gekürzt.

DB-Migration v2 → v3 erfolgt beim nächsten Öffnen durch die App. Vorher Backup anlegen, Server für den Wechsel stoppen.
Historische `claude`-Werte bleiben erhalten. Neue Werte haben Quelle `openai`; beide stehen unter `regel` und `portal`.
`extraction_run` protokolliert Quelle, effektive Modellwahl aus dem CLI-Protokoll, Text-Hash und Zeitpunkt für neue Speicherungen.
Ist die Modellangabe im CLI-Protokoll nicht verfügbar, wird der konfigurierte Name verwendet (bei null bleibt die Spalte leer).
Bestehende erfolgreiche Extraktionen bleiben gültig. Eine explizite Neuauswertung ersetzt die bisherigen KI-Felder des Objekts.
Für Rückkehr zum alten Code nach Migration zuerst den Server stoppen, das DB-Backup wiederherstellen
und den neuen `ki`-Block aus settings.yaml entfernen (alter Code versteht weder DB v3 noch diesen Block).

Testdatenbank: `run.ps1 -Db <absoluter Pfad> -ConfigDir <absoluter config-Pfad>`;
diese Angaben werden auch vom Server-Runner weitergereicht. Nie die Produktivdatenbank mit Testanzeigen befüllen.
Nach der Umstellung den laufenden Server neu starten. Windows-Aufgaben und Passwörter werden dabei nicht geändert.

Inbetriebnahme 03.11.2026: Backup unter `data/backup/vor-codex-20261103-210043/`, Produktiv-DB von v2 auf v3 migriert,
alle 368 Extraktionswerte erhalten. Server auf 8710 gestartet. Vier Testanzeigen mit echtem Codex ausgewertet (0 abgelehnt),
eine Neuauswertung über run.ps1 einschließlich Bewertung mit Exit 0 geprüft. Abschließend 172 Tests grün.

### 8.1 KI-Konfiguration und Hilfsbefehle

```yaml
ki:
  cli_pfad: null        # automatische Suche; alternativ absoluter Pfad zur codex.exe
  modell: null          # CLI-Standard ohne Benutzerkonfiguration; Modellname zum Pinnen
  zeitlimit_s: 1800     # 1–3600, über alle Stapel und Korrekturen
  stapelgroesse: 20     # 1–20 Angebote
  max_stapel: 3        # 1–3 Stapel je Lauf
```

`scripts/extract.py` liefert Exit 0 bei vollständiger erfolgreicher Verarbeitung, Exit 2 bei KI-Teilfehlern
oder offenen Restangeboten. Konfigurationsfehler ergeben Exit 1; ungültige Argumente werden vom Argumentparser abgelehnt.
In `run.ps1` wird ein nicht erfolgreicher KI-Schritt zum Teilfehler; die Bewertung läuft anschließend weiter.
`scripts/pending.py` und `scripts/save.py` bleiben Diagnose-/Importhilfen. Ein manueller Import über `save.py`
speichert die Quelle `openai`, kann aber ohne CLI-Aufruf kein effektives Modell ermitteln.

Der Spezial-Backupordner `vor-codex-…` enthält nur die eigene DB und Konfiguration, keinen Fredy-Schnappschuss.
Er ist kein regulärer Backup-Lauf in `run_log` und ersetzt weder tägliche Backups noch die Phase-6-Abnahme.
Im Migrationstest wurden Anmeldung, erfolgreiche Codex-Antwort und Neuauswertung geprüft; ein echtes
Nutzungslimit oder die Aufgabenplanung unter gesperrtem Bildschirm wurden dabei nicht ausgelöst/getestet.

### 8.2 Codex wird im Web-Lauf nicht gefunden

`job-6.log` vom 03.11.2026 zeigte „Codex CLI fehlt“: Der manuell gestartete Server hatte den
Suchpfad der Desktop-App nicht geerbt. Seit der Korrektur wird zuerst `ki.cli_pfad` verwendet,
falls gesetzt, sonst `PATH`, danach die benutzerlokale Windows-CLI-Installation und der
versionierte App-Cache unter `AppData/Local/OpenAI/Codex/bin/*/codex.exe`.
Im Cache wird die zuletzt geänderte ausführbare Datei gewählt. Kein fester Versionshash ist hinterlegt.
Die Installer-Installation liegt unter `AppData/Local/Programs/OpenAI/Codex/bin`.
Ein ungültiger expliziter Pfad ergibt einen Fehler statt still auf ein anderes Programm auszuweichen.
Den gewählten Programmpfad zeigt das Laufprotokoll als `Codex-CLI: …`.

Bei einer anderen Installation `ki.cli_pfad` auf den tatsächlichen Pfad setzen.
Windows-Suchpfad oder Aufgaben müssen dafür nicht geändert werden. Python lädt die Konfiguration
bei jedem Extraktionsaufruf neu; für diese Korrektur muss der bestehende Webserver nicht neu gestartet werden.
CLI-Fehler wie „Modell derzeit ausgelastet“ erscheinen nun zusätzlich im Job-Log; Details bleiben im Codex-Protokoll.

Verifiziert: Neuauswertung über run.ps1 auf separater DB mit bewusst aus `PATH` entferntem Codex,
anschließende Bewertung, Exit 0. Vollständige Testsuite nach Korrektur: 178 Tests grün.
Der manuell gestartete Server wurde dabei nicht gestoppt oder neu gestartet.

### 8.3 Ungültiger Feldwert in einer gültigen Antwort

`job-7.log` (03.11.2026): Bei Angebot 58 kam `wert_json: "Gastherme"` statt des darin
JSON-kodierten Textwerts. Der zusätzliche JSON-Parser brach zuvor den ganzen Stapel 56–59 ab.
Seit der Korrektur werden eindeutig zuordenbare Ergebnisse getrennt normalisiert: 56, 57 und 59
werden gespeichert, nur 58 wird einmal mit konkreter Fehlermeldung erneut vorgelegt.
Textwerte werden nicht ungeprüft automatisch umgedeutet. Scheitert die Korrektur erneut, endet der
KI-Schritt mit Teilfehler; bisherige Werte dieses Angebots bleiben erhalten. Der nächste Lauf kann
es entsprechend Versuchszähler erneut vorlegen. Die Korrektur ist im Job-Log als `ki_korrektur`
bzw. `ki_abgelehnt` sichtbar. Die Prompt-Anweisung enthält ein ausdrückliches Beispiel für Textwerte.

Verifiziert: Die tatsächliche fehlerhafte Antwort wurde auf einer Kopie der Produktiv-DB nachgespielt;
erster Stapel 56–59, Korrektur nur für 58, danach 4 angenommen, 0 abgelehnt, 0 Felder verworfen und 0 offen.
Der Korrekturschritt wurde dabei deterministisch vorgegeben, nicht neu von OpenAI erzeugt.
181 Tests grün. Keine produktive Neuauswertung und kein Server-Neustart für diese Prüfung.
