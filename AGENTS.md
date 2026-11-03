# AGENTS.md – Einstieg für neue Sitzungen

Persönliche Meta-Suche für Kapitalanlage-Immobilien (Start: Mehrfamilienhäuser). Fredy (Docker) sammelt Angebote, dieses Projekt filtert, extrahiert (Regeln + Codex-Skill), bewertet und meldet.

**Maßgeblich ist [PLAN.md](PLAN.md).** Stand der Umsetzung: PLAN.md, Abschnitt 13.1. Offene Punkte: Abschnitt 14. Einrichtung des Mini-PCs: [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md). Server und MCP: [docs/SERVER.md](docs/SERVER.md).

## Wo wir stehen (zuletzt aktualisiert 03.11.2026)

- **Neueste Korrektur (job-7):** `wert_json` war bei Angebot 58 unkodierter Text „Gastherme“. Jetzt `normalisiere_stapel()` mit Einzelfehlern: gültige Ergebnisse speichern, nur betroffene Angebote einmal korrigieren, Fehlerstatus ohne Löschen alter Werte, Rohantworten als `*.antwort.json`. Originalantwort auf DB-Kopie mit vorgegebener Korrektur nachgespielt: alle 4 angenommen, 0 Fehler; 181 Tests grün. Produktions-DB und manueller Server blieben unverändert. Details docs/SERVER.md Abschnitt 8.3.

- **Korrektur nach Web-Test:** job-6 scheiterte an fehlendem Codex im PATH. `finde_codex()` sucht nun zusätzlich die benutzerlokale Windows-CLI und den App-Cache; optional `settings.ki.cli_pfad`. Gewählter Pfad und konkrete CLI-Fehler stehen im Job-Log. Echter run.ps1-Test mit entferntem Codex-PATH auf Test-DB: Exit 0. 178 Tests grün. Server blieb im manuellen Terminal unverändert; neue Extraktionsprozesse laden den korrigierten Code selbst. docs/SERVER.md Abschnitt 8.2.

- **Fertig:** Phasen 2–4, 7, 8, 8b und 8c (ohne Telegram/Digest). Finanzkennzahlen und Score werden deterministisch in Python berechnet. Objekt-Simulation nur Jahr 1 und nur Oberfläche; vereinfachte Steuern nur Anzeige/KPI, Score vor Steuern.
- **KI-Anbindung:** `run.ps1` → `scripts/extract.py` → `codex exec` mit gespeicherter ChatGPT-Anmeldung. Python steuert Auswahl, Stapel, Prüfung und Speicherung. `settings.ki` steuert Modell, Gesamtzeitlimit und Stapelgrenzen. Ressourcen: `resources/extraktionsregeln.md` und `resources/extraction_schema/`. Claude-CLI, `.claude/run-settings.json` und Claude-Token werden nicht mehr genutzt.
- **Verifiziert am 03.11.2026:** 172 Tests grün. Vier Testanzeigen mit echtem Codex ausgewertet, 0 abgelehnt und 0 Felder verworfen; Neuauswertung über run.ps1 inklusive Bewertung mit Exit 0. Effektives Modell im Test `gpt-6.1-sol` (CLI-Standard, konfigurierbar). Produktive Anzeigen wurden bei der Migration nicht neu ausgewertet.
- **DB v3 und Sicherung:** Produktiv-DB von v2 auf v3 migriert, alle 368 Extraktionswerte erhalten. Sicherung davor: `data/backup/vor-codex-20261103-210043/` (eigene DB und Konfiguration, kein vollständiges Fredy-Backup). Neue Werte haben Quelle `openai`, historische `claude`-Werte bleiben erhalten; `extraction_run` protokolliert Quelle, effektives Modell soweit ermittelbar, Text-Hash und Zeitpunkt. Der Anbieterwechsel allein macht erfolgreiche Extraktionen nicht ungültig.
- **Server:** Am 03.11.2026 auf Port 8710 von Hand gestartet; `/health` erfolgreich und Login HTTP 200. Zugangsdaten in `.env` bestehen. Dauerhafter Start über Aufgabenplanung und Tailscale sind damit nicht eingerichtet. Aktueller Betrieb: [docs/SERVER.md](docs/SERVER.md).
- **Phase 6 umgesetzt, Abnahme offen:** Läufe, Backup und Server-Aufgabe können mit `scripts/install_tasks.ps1` eingerichtet werden; **das macht der Nutzer selbst** (docs/SERVER.md Abschnitt 7). Zuletzt am 20.10.2026 geprüft: keine Aufgabe „immo-search*“. Bei der KI-Migration wurden keine Aufgaben geändert. Die Abnahmewoche unter Aufgabenplanung und gesperrtem Bildschirm ist noch nicht nachgewiesen. Der Migrationstest ersetzt diese Abnahme nicht.
- **Fredy / Phase 1:** Mini-PC AI-HOME, Windows 11; Repo `C:\E\ai-workspace\immo-search`, Fredy-Daten `C:\E\docker\fredy`, Fredy 29.3.0 unter http://localhost:9998. Einrichtung und datierte Diagnose: docs/SETUP-MINIPC.md Abschnitte 8–9. Aktives Profil `mfh-kl` (Kaiserslautern, 5 km, 300 000–2 000 000 €, RP, EK nur Nebenkosten, Schätzmiete 9 €/m²). Immowelt lieferte beim Ersttest HTTP 403; Nutzer will unabhängig davon fortfahren.
- **Offenes Risiko jetzt prüfen:** Fredy-Aufbewahrung `listingRetentionDays = 14` kann ab 01.11.2026 den Status „entfernt“ verfälschen. Diese Prüfung wurde bei der KI-Migration nicht durchgeführt (docs/SETUP-MINIPC.md Abschnitt 9).
- **Finanzkonfiguration:** Zins 0.048, Tilgung 0.015; Steuern: Grenzsteuersatz 0.42, Gebäudeanteil 0.80, AfA 0.02. `SCORING_VERSION = 2` ist von DB v3 und Fachschema v1 unabhängig.
- **Entscheidungen:** Leerstand gilt als Mietpotenzial; Schätzmiete/Ranking bleiben. Bauprojekte werden ausgeschlossen. Duplikate über Portale werden gruppiert. Provision „zzgl. MwSt.“ wird mit 1,19 umgerechnet. Objekt-Simulation bleibt Jahr 1 ohne MCP. Passwörter, Anmeldungen und Windows-Einstellungen macht der Nutzer selbst.
- **Nächste Schritte:** Aufgaben einrichten und einwöchige Phase-6-Abnahme starten; Fredy-Aufbewahrung sowie Portale prüfen und Phase 1 abschließen; danach Phase 5 (Telegram/E-Mail-Digest). Phase 9 nach Bedarf. Die alte Aufforderung zum Server-Neustart vor Phase 8b ist erledigt.
- **Testbetrieb:** Eigene Test-DB und Konfiguration mit `--db`/`--config-dir` weitergeben, bei `run.ps1` mit `-Db`/`-ConfigDir`. Alte Dev-Startdatei `.claude/launch.json` war eine lokale Claude-App-Konfiguration; keine aktuelle Codex-Startanleitung daraus ableiten. Dev-Server nur mit Test-Zugang per Prozess-Umgebung, nie mit fremdem Passwort und produktiver `.env` starten. Bei MSIX-Umleitung `UV_PYTHON_INSTALL_DIR` auf die vorhandene Python-Installation setzen (hier `C:/Users/lhenr/.uv-python`).

### Historische Läufe vor dem Wechsel

- 18.10.2026: 48 Angebote; Regeln und **Claude**-Extraktion, alle angenommen.
- 19.10.2026: run.ps1 mit **Claude Code** erfolgreich; 3 neue Angebote (49–51) ausgewertet, Angebot 51 als Bauprojekt erkannt. Die damalige dontAsk-Einzelbefehlsproblematik betrifft den entfernten Claude-Lauf und ist keine offene Codex-Aufgabe.
- 20.10.2026: 51 Angebote nach Phase 8c neu bewertet, 27 ausgeschlossen; Scores unverändert. Diese Zählung ist historisch, kein aktueller Bestandsstand.

## Arbeitsweise

- Sprache: **Deutsch** in Gesprächen, Doku, Kommentaren, Fehlermeldungen und Commit-Nachrichten. Bezeichner im Code ebenfalls deutsch (`preis`, `bewerte`, `kaufpreisempfehlung`), technische Standardbegriffe englisch.
- **Erst committen, wenn der Nutzer es sagt.** Commit-Nachrichten auf Deutsch: Betreff, Leerzeile, Stichpunkte, am Ende `Co-Authored-By: Codex …`. Remote: `origin` = https://github.com/lukas-1985/immo-search.git, Branch `main`.
- Werkzeuge: Python 3.12 mit **uv** (`uv sync`, `uv run pytest -q`, `uv run python scripts/<name>.py`). Tests müssen vor jedem Commit grün sein.
- Nach jeder Phase: PLAN.md (Status-Zeile oben, 13.1, betroffene Abschnitte), README.md „Stand“ und diese Datei aktualisieren.
- Ausprobieren ohne Fredy: `uv run python scripts/dev_seed.py --db data/dev.db` lädt die Testanzeigen aus `tests/fixtures/mfh_anzeigen.json`. Alle Skripte nehmen `--db` und `--config-dir`. Nie in die echte `data/immo.db` seeden.
- Grundsätze aus dem Plan:
  - Eine Logik in `src/immo/`, die Skripte unter `scripts/` sind dünn.
  - Deterministische Bewertung, Codex wertet jedes Angebot nur einmal aus.
  - Regelwerte haben Vorrang vor Codex, deshalb gilt beim Parser: „lieber nichts finden als falsch finden“.
  - Fredys DB wird nie beschrieben.

## Code-Landkarte

| Datei | Inhalt |
|---|---|
| `src/immo/config.py` | Pydantic-Modelle für `settings.yaml` und Profile, `load_config`, `finance_for` (Defaults + Profil) |
| `src/immo/db.py` | Schema und Migrationen (`PRAGMA user_version`, derzeit v3), WAL |
| `src/immo/fredy_client.py` | API-Client (Session-Login) und SQLite-Client (read-only), `listing_from_row`, `resolve_jobs` |
| `src/immo/sync.py` | Sync aller Profil-Jobs, `fetch_filter` nur für neue Zuordnungen, Preisverlauf, „entfernt“, ruft am Ende die Duplikaterkennung |
| `src/immo/duplicates.py` | Duplikate über Portale → `duplicate_group` (Union-Find, Workflow-Übernahme) |
| `src/immo/filters.py` | `fetch_filter` (Stufe 2) |
| `src/immo/extraction.py` | Schema laden, Belegstellen- und Plausibilitätsprüfung, `store_fields` mit Quellen-Rang |
| `src/immo/parse_attrs.py` | Regel-Parser (Quelle `regel`) |
| `src/immo/ki_io.py` | `pending` / `save`, Quellen, `extraction_status` und `extraction_run` |
| `src/immo/codex_extraktion.py` | Codex-Aufruf, strukturierte Antworten, Stapel, Korrekturversuch, Zeitlimit und Logs |
| `scripts/extract.py` | dünner CLI-Einstieg für die KI-Extraktion |
| `src/immo/finance.py` | `Annahmen`, `simulate()` (inkl. Steuern vereinfacht: AfA, Einkünfte, Steuer, Cashflow nach Steuern), Kaufpreisempfehlung (geschlossene Formel, Zinsspanne), `loese()` für die Zielwert-Rückrechnung |
| `src/immo/kpis.py` | KPI-Register und Normalisierung |
| `src/immo/scoring.py` | Ausschlusskriterien, Score (gewichtet oder sichere Formel), `run_score`, `ranking` |
| `src/immo/fredy_check.py` | Diagnose gegen das laufende Fredy (Phase 1) |
| `src/immo/queries.py` | Lesende Abfragen für Oberfläche und MCP: `liste` (je Duplikatgruppe eine Zeile), `detail`, `uebersicht`, `aenderungen`, `statistik` |
| `src/immo/workflow.py` | Status (an der Duplikatgruppe) und Notizen, Quelle ui/mcp/system |
| `src/immo/jobs.py` | Job-Warteschlange und Runner-Thread (`lauf`, `neu_auswerten`, `bewerten`), nur feste Befehle; `direkt_ausfuehren` für zeitgesteuerte Läufe |
| `src/immo/backup.py` | Backup: `immo.db` per Backup-API, `config/`, Fredys DB als geprüfter Schnappschuss (nur kopiert, nie geöffnet), Aufbewahrung |
| `src/immo/health.py` | Health-Prüfung (Portale, Sync, Backup, `/health`) → `run_log` |
| `src/immo/simulation.py` | Ranking-Simulation im Speicher, `als_yaml` für „Als Profil übernehmen“ |
| `src/immo/objekt_simulation.py` | Objekt-Simulation (8b): `lade_basis` (wie `scoring.basis_annahmen`), `aus_formular`, `rechne`, `loese_ziel` (→ `finance.loese`), Szenarien (Tabelle `scenario`) |
| `src/immo/config_edit.py` | Konfigurations-Editor: Prüfung in Kopie, Diff, Backup, `config_change`; `setze_werte` ändert Werte im Text (Kommentare bleiben) |
| `src/immo/server/` | FastAPI-App (`app.py`), Routen (`web.py`), Jinja-Vorlagen, CSS, Login/CSRF/Bearer (`auth.py`), MCP-Werkzeuge (`mcp_tools.py`, SDK `mcp` 2.x: `MCPServer`) |
| `run.ps1`, `src/immo/codex_extraktion.py` | Unbeaufsichtigter Lauf und Rechte des Codex-Laufs |
| `scripts/install_tasks.ps1`, `scripts/aufgabe.ps1` | Windows-Aufgabenplanung anlegen; Einstieg der Aufgaben (Logs `data/logs/aufgabe-*.log`, Server-Neustartschleife) |
| `.agents/skills/immo-analyse/`, `resources/` | Skill (`SKILL.md`) und Extraktionsschema MFH |

## Wissen über Fredy (Recherche 18.10.2026, Quellcode auf GitHub)

**Version und Betrieb**
- Im Projekt festgelegt ist **29.3.0** (17.10.2026), in der Compose-Datei fest eingetragen.
- Seit 29.2.2 läuft das Image als Nicht-Root-Benutzer. Bei Problemen die Rechte der Bind-Mounts prüfen.
- Immowelt und Kleinanzeigen liest Fredy über einen Headless-Browser, daher `shm_size: 1gb`.
- IS24 läuft über die inoffizielle Mobile-API. **Gewerbliche Suchen werden nicht unterstützt**, vermutlich auch „Anlageobjekte“ nicht. Deshalb „Haus kaufen → Mehrfamilienhaus“ testen (offener Punkt 4).
- `/conf/config.json` enthält nur den DB-Pfad, alles andere steht in Fredys DB. Analytics ist opt-in. Standard-Login `admin`/`admin`.

**API**
- Login über `POST /api/login` mit `{username, password}`, danach Session-Cookie.
- `GET /api/jobs` liefert eine Liste.
- `GET /api/listings/table` mit `page`, `pageSize`, `sortfield`, `sortdir`, `jobNameFilter` (Wert = Job-ID, `jobIdFilter` wird ignoriert). Die Zeilen stehen unter `result`.

**Tabelle `listings`**
- Spalten u. a. `id, hash, provider, job_id, price, size, rooms, build_year, energy_class, title, image_url, description, address, link, created_at, is_active, latitude, longitude, published_at, price_per_sqm, manually_deleted`.
- Dazu `previous_price`, `price_changed_at`, `market_median_sqm`, `market_sample_size`. Damit ließe sich der KPI `preis_m2_vs_markt` umsetzen.
- Die Portal-IDs sind `immoscout`, `immowelt`, `kleinanzeigen`.

**Ungeprüft, mit `check_fredy.py` am echten System klären**
- Heißen die Felder der API-Antwort genauso wie die DB-Spalten? `listing_from_row` liest snake_case und camelCase.
- Liefert `/table` auch inaktive Angebote?
- In welchem Format kommt `created_at`?
- Duplikat-Kennung über Portale: Fredy liefert keine (geprüft 18.10.2026), eigene Erkennung in `duplicates.py`.
- Sind die Beschreibungen je Portal vollständig?

## Bekannte Grenzen

- Abnahmekriterium Phase 3 mit **echten Anzeigen** (18.10.2026): 22 der 48 Anzeigen nennen eine Miete, bei 21 ist die Ist-Miete erkannt (95 %; Regeln 13, Claude 8 (vor der Migration)). Die Ausnahme (Angebot 35) nennt nur die Ladenmiete. Nur 21 der 48 Angebote haben damit überhaupt eine Ist-Miete, der Rest wird mit `miete_schaetzung_eur_m2` geschätzt.
- Regel `wohneinheiten` lag zweimal falsch („Neubaukonzept für 7 Wohneinheiten“, „5 Wohnungen … vermietet“). Korrigiert und getestet; weitere solche Fälle sind möglich.
- Ohne `finance.bundesland` im Profil rechnet die Grunderwerbsteuer mit 0 %. Das wird als Hinweis angezeigt.
- Benachrichtigungen und Digest (Phase 5) fehlen noch; MCP-Werkzeug `send_digest_now` und der Digest-Button sind deshalb nicht vorhanden. Die Objekt-Simulation (8b) rechnet bewusst nur Jahr 1 und hat kein MCP-Werkzeug (PLAN.md 10.2 Nr. 4). Die Steuerrechnung (8c) ist eine grobe Näherung: fester AfA-Satz, Bewirtschaftung voll als Werbungskosten, kein Soli, keine Kirchensteuer.
- Historischer Mengentest mit Claude am 18.10.2026: `pending.py` lieferte höchstens 20 Angebote; 48 Angebote wurden in drei Durchgängen ausgewertet (Dateien `data/extraction/2026101*.json`), 0 abgelehnt.

- Codex ist auf vier Testanzeigen und eine gezielte Neuauswertung geprüft; eine vollständige erneute Auswertung des produktiven Bestands und die einwöchige Automatisierungsabnahme sind damit nicht belegt.
