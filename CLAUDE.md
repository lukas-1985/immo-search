# CLAUDE.md – Einstieg für neue Sitzungen

Persönliche Meta-Suche für Kapitalanlage-Immobilien (Start: Mehrfamilienhäuser). Fredy (Docker) sammelt Angebote, dieses Projekt filtert, extrahiert (Regeln + Claude-Skill), bewertet und meldet.

**Maßgeblich ist [PLAN.md](PLAN.md).** Stand der Umsetzung: PLAN.md, Abschnitt 13.1. Offene Punkte: Abschnitt 14. Einrichtung des Mini-PCs: [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md). Server und MCP: [docs/SERVER.md](docs/SERVER.md).

## Wo wir stehen (zuletzt aktualisiert 20.10.2026)

- **Fertig:** Phasen 2–4 (Sync, Extraktion, Scoring mit Kaufpreisempfehlung) und Phasen 7–8 (immo-server: Oberfläche, MCP, Workflow, Job-Runner, Ranking-Simulation, Konfigurations-Editor; ohne Digest-Teile). Phase 8b (19.10.2026, Umfang mit dem Nutzer verkleinert): Objekt-Simulation für Jahr 1 mit Zielwert-Rückrechnung und Szenarien, nur Oberfläche, kein MCP. Phase 8c (20.10.2026): Cashflow nach Steuern vereinfacht (PLAN.md 5.7), nur Anzeige und KPI, Score bleibt vor Steuern. 160 Tests grün.
- **Phase 6 umgesetzt (19.10.2026), Abnahme offen:** `run.ps1` (Sync → Regeln → `claude -p "/immo-analyse … --nur-extraktion"` → Bewertung → Health, Sperrdatei, Zeitlimit) mit `.claude/run-settings.json` (`--permission-mode dontAsk`). `scripts/install_tasks.ps1` legt die Aufgaben „immo-search lauf/backup/server“ an (über `scripts/aufgabe.ps1`; Läufe über `scripts/lauf.py` als Job „zeitplan“); **das richtet der Nutzer selbst ein**, docs/SERVER.md Abschnitt 7. Backup `scripts/backup.py`, Health `scripts/health.py` (Ergebnis in `run_log`, Telegram-Alarm erst mit Phase 5). Danach eine Woche beobachten. Claude Code CLI 2.1.302 per winget installiert und angemeldet (claude.ai, geprüft 19.10.2026). **Aufgaben sind noch nicht eingerichtet** (Stand 20.10.2026: keine Aufgabe „immo-search*“), deshalb gab es auch noch kein Backup und die Woche zur Abnahme läuft noch nicht.
- **Lauf von Hand mit `run.ps1` (19.10.2026, 21:49):** Exit 0, gut 1 Minute. Sync 52 geholt, 3 neu (Angebote 49–51), Claude hat alle 3 ausgewertet (51 = OKAL-Fertighaus → Bauprojekt), 51 bewertet, 27 ausgeschlossen. Health-Warnungen: Immowelt hat noch nie ein Angebot geliefert, Backup noch nie gelaufen. Auffällig: Mit `dontAsk` wurde ein zusammengesetzter Befehl von Claude (`save.py …; "EXIT …"`) abgelehnt. Claude ist auf den einfachen Befehl ausgewichen. Idee (offen): in der SKILL.md auf einfache Einzelbefehle hinweisen. Protokoll: `data/logs/hand-lauf-20261019.log`.
- **Erster echter Lauf (18.10.2026):** 48 Angebote in `data/immo.db` (sync zweimal, 2. Lauf neu = 0), Regeln + Claude-Extraktion für alle 48 (0 abgelehnt), `score.py` gelaufen. Extraktionsdateien unter `data/extraction/`.
- **Phase 1 fast fertig:** Der Mini-PC (AI-HOME, Lenovo ThinkCentre, Windows 11 direkt auf der Hardware) ist eingerichtet: WSL 2.7.13, Docker Desktop 4.95, uv. Es gibt nur Laufwerk C:. Das Repo liegt unter `C:\E\ai-workspace\immo-search`, Fredys Daten unter `C:\E\docker\fredy`. Fredy 29.3.0 läuft unter http://localhost:9998. Passwort steht in `.env`.
  - Aktives Profil `mfh-kl` (Kaiserslautern, 5 km, 300 000–2 000 000 €, RP, EK = nur Nebenkosten, Miete 9 €/m²). Fredy-Jobs „MFH KL – IS24/Immowelt/Kleinanzeigen“, Analytics aus, Arbeitszeit 07–22 Uhr, Intervall 60 Min., `provider_details` für alle drei Portale.
  - Ergebnisse der Diagnose: Tabelle in [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md), Abschnitt 8. Such-URLs, Fredy-Einstellungen und nützliche Fredy-API-Endpunkte: Abschnitt 9.
  - **Offenes Risiko:** Fredy löscht Angebote nach `listingRetentionDays` = 14. Ab 01.11.2026 prüfen, ob `sync` sie dann fälschlich als „entfernt“ markiert (Anleitung, Abschnitt 9).
- **Server-Inbetriebnahme (Stand 19.10.2026):** `UI_PASSWORD_HASH`, `SESSION_SECRET` und `MCP_TOKEN` hat der Nutzer in `.env` gesetzt. **Offen:** Server läuft nicht dauerhaft (Start von Hand: `uv run python scripts/serve.py`, Stoppen: Strg+C oder Prozess auf Port 8710 beenden). Der laufende Prozess auf 8710 stammt von vor Phase 8b und muss für „Simulieren“ **neu gestartet** werden. Tailscale fehlt. Anleitung: docs/SERVER.md.
- **`config/settings.yaml`:** `finance_defaults` Zins 0.048 und Tilgung 0.015 (vorher 0.038 / 0.02) hat der Nutzer am 19.10.2026 um 21:57 geändert und neu bewertet. Beim Commit von 8b auf seinen Wunsch ausgelassen. Mit 8c kommt der Block `steuern` dazu (Gebäudeanteil 0.80, AfA 0.02 statt "auto"). Im Repo steht noch `afa_satz: auto` und Gebäudeanteil 0.75. Der Code liest „auto“ als 2 %, ein frischer Checkout rechnet also mit 75 % Gebäudeanteil, bis die Datei committet ist. Ob die Datei committet wird, entscheidet der Nutzer.
- **Neu bewertet (20.10.2026):** Mit 8c ist `SCORING_VERSION` = 2, die Steuerwerte stehen im `config_hash`. `data/immo.db` ist danach mit `score.py` neu bewertet: 51 bewertet, 27 ausgeschlossen, Scores unverändert, die Steuerzeile ist jetzt gespeichert.
- **Entscheidungen des Nutzers:** Immowelt-Bot-Schutz vorerst ignorieren. Leerstand = Mietpotenzial (Ranking nicht korrigieren). Job-Runner gleich mit Claude (nicht erst in Phase 6). Phase 8b erst nach 7 und 8. Phase 8b am 19.10.2026 verkleinert: nur Jahr 1, Zielwert-Rückrechnung (Cashflow, Bruttorendite, Nettoanfangsrendite → Kaufpreis, Miete, Zins, EK), Szenarien speichern, Neuberechnung per Button (ohne JS), kein MCP. Er möchte, dass Claude Einrichtungsschritte selbst ausführt, wo das zulässig ist. Passwörter, Anmeldungen und Windows-Einstellungen macht er selbst.
- **Nächster Schritt:**
  0. Server auf 8710 neu starten und die Objekt-Simulation selbst ausprobieren (Detailansicht → „Simulieren“). Aufgaben mit `scripts/install_tasks.ps1` einrichten (Nutzer, docs/SERVER.md Abschnitt 7), damit Backup und die Phase-6-Woche starten.
  1. Immowelt beobachten: Beim ersten Lauf meldete Fredy „detected as a bot“ (HTTP 403). Der Nutzer will unabhängig davon weitermachen.
  2. Erkenntnisse aus dem ersten Lauf:
     - Erledigt: **Bauprojekte** (Fertighaus-/Ausbauhaus-Angebote) über das Schemafeld `bauprojekt` (Regel + Claude) und `hard_filter bauprojekt == false` ausgeschlossen, alle 8 im Bestand erkannt. Schema-Version bewusst nicht erhöht (additives, optionales Feld, sonst müsste Claude alles neu auswerten).
     - Entschieden: **Leerstand** gilt dem Nutzer grundsätzlich als positiv (Mietpotenzial). Das Ranking mit Schätzmiete bleibt, auch wenn ein leeres Haus vorn steht.
     - Erledigt: **Duplikate** über Portale (`duplicates.py`): gleiche PLZ, Titel ≥ 90 % ähnlich, Preis ± 5 %, Fläche ± 2 %, verschiedene Portale. Läuft am Ende jedes Syncs, Gruppe = kleinste ID, Workflow-Status wandert bei Zusammenlegung mit. `ranking` zeigt je Gruppe nur das beste Angebot. Im Bestand 7 Paare, keine Fehltreffer.
     - Erledigt: Provision „zzgl. MwSt.“ wird × 1,19 gerechnet (Regel mit Rechenweg, Hinweis im Skill). Angebot 39: 4,25 %.
  3. Nach 2–3 Tagen `check_fredy.py` und `sync.py` erneut ausführen (Anleitung, Abschnitt 7), dann Phase 1 abschließen.
- **Danach:** Phase 5 (Telegram + E-Mail-Digest, dann `send_digest_now` und Digest-Button), Phase 6 abnehmen (eine Woche unbeaufsichtigt). Phase 9 nur nach Bedarf (dort liegen jetzt auch Mehrjahresverlauf, Steuern, IRR, Tornado und MCP für die Objekt-Simulation).
- **Dev-Server zum Ausprobieren:** `.claude/launch.json` (nicht im Repo) startet `immo-dev-8b` auf Port 8711 mit `data/dev-8b.db` (Kopie) und eigenem Test-Passwort aus `data/dev-zugang.txt`.
- **Hinweis für Sitzungen in der Claude-Desktop-App:** Der Server-Prozess erbt die MSIX-Umleitung von AppData; `UV_PYTHON_INSTALL_DIR` setzen (siehe Memory). Den Dev-Server nie mit der echten `.env` und fremdem Passwort starten: Test-Zugang nur per Umgebungsvariablen des Prozesses.

## Arbeitsweise

- Sprache: **Deutsch** in Gesprächen, Doku, Kommentaren, Fehlermeldungen und Commit-Nachrichten. Bezeichner im Code ebenfalls deutsch (`preis`, `bewerte`, `kaufpreisempfehlung`), technische Standardbegriffe englisch.
- **Erst committen, wenn der Nutzer es sagt.** Commit-Nachrichten auf Deutsch: Betreff, Leerzeile, Stichpunkte, am Ende `Co-Authored-By: Claude …`. Remote: `origin` = https://github.com/lukas-1985/immo-search.git, Branch `main`.
- Werkzeuge: Python 3.12 mit **uv** (`uv sync`, `uv run pytest -q`, `uv run python scripts/<name>.py`). Tests müssen vor jedem Commit grün sein.
- Nach jeder Phase: PLAN.md (Status-Zeile oben, 13.1, betroffene Abschnitte), README.md „Stand“ und diese Datei aktualisieren.
- Ausprobieren ohne Fredy: `uv run python scripts/dev_seed.py --db data/dev.db` lädt die Testanzeigen aus `tests/fixtures/mfh_anzeigen.json`. Alle Skripte nehmen `--db` und `--config-dir`. Nie in die echte `data/immo.db` seeden.
- Grundsätze aus dem Plan:
  - Eine Logik in `src/immo/`, die Skripte unter `scripts/` sind dünn.
  - Deterministische Bewertung, Claude wertet jedes Angebot nur einmal aus.
  - Regelwerte haben Vorrang vor Claude, deshalb gilt beim Parser: „lieber nichts finden als falsch finden“.
  - Fredys DB wird nie beschrieben.

## Code-Landkarte

| Datei | Inhalt |
|---|---|
| `src/immo/config.py` | Pydantic-Modelle für `settings.yaml` und Profile, `load_config`, `finance_for` (Defaults + Profil) |
| `src/immo/db.py` | Schema und Migrationen (`PRAGMA user_version`, derzeit v2), WAL |
| `src/immo/fredy_client.py` | API-Client (Session-Login) und SQLite-Client (read-only), `listing_from_row`, `resolve_jobs` |
| `src/immo/sync.py` | Sync aller Profil-Jobs, `fetch_filter` nur für neue Zuordnungen, Preisverlauf, „entfernt“, ruft am Ende die Duplikaterkennung |
| `src/immo/duplicates.py` | Duplikate über Portale → `duplicate_group` (Union-Find, Workflow-Übernahme) |
| `src/immo/filters.py` | `fetch_filter` (Stufe 2) |
| `src/immo/extraction.py` | Schema laden, Belegstellen- und Plausibilitätsprüfung, `store_fields` mit Quellen-Rang |
| `src/immo/parse_attrs.py` | Regel-Parser (Quelle `regel`) |
| `src/immo/claude_io.py` | `pending` / `save` (Schnittstelle zum Skill), `extraction_status` |
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
| `run.ps1`, `.claude/run-settings.json` | Unbeaufsichtigter Lauf und Rechte des Claude-Laufs |
| `scripts/install_tasks.ps1`, `scripts/aufgabe.ps1` | Windows-Aufgabenplanung anlegen; Einstieg der Aufgaben (Logs `data/logs/aufgabe-*.log`, Server-Neustartschleife) |
| `.claude/skills/immo-analyse/` | Skill (`SKILL.md`) und Extraktionsschema MFH |

## Wissen über Fredy (Recherche 18.10.2026, Quellcode auf GitHub)

**Version und Betrieb**
- Aktuell ist **29.3.0** (17.10.2026), in der Compose-Datei fest eingetragen.
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

- Abnahmekriterium Phase 3 mit **echten Anzeigen** (18.10.2026): 22 der 48 Anzeigen nennen eine Miete, bei 21 ist die Ist-Miete erkannt (95 %; Regeln 13, Claude 8). Die Ausnahme (Angebot 35) nennt nur die Ladenmiete. Nur 21 der 48 Angebote haben damit überhaupt eine Ist-Miete, der Rest wird mit `miete_schaetzung_eur_m2` geschätzt.
- Regel `wohneinheiten` lag zweimal falsch („Neubaukonzept für 7 Wohneinheiten“, „5 Wohnungen … vermietet“). Korrigiert und getestet; weitere solche Fälle sind möglich.
- Ohne `finance.bundesland` im Profil rechnet die Grunderwerbsteuer mit 0 %. Das wird als Hinweis angezeigt.
- Benachrichtigungen und Digest (Phase 5) fehlen noch; MCP-Werkzeug `send_digest_now` und der Digest-Button sind deshalb nicht vorhanden. Die Objekt-Simulation (8b) rechnet bewusst nur Jahr 1 und hat kein MCP-Werkzeug (PLAN.md 10.2 Nr. 4). Die Steuerrechnung (8c) ist eine grobe Näherung: fester AfA-Satz, Bewirtschaftung voll als Werbungskosten, kein Soli, keine Kirchensteuer.
- Claude-Extraktion in größerem Umfang: `pending.py` liefert höchstens 20 Angebote. Beim ersten Lauf hat Claude 48 Angebote in drei Durchgängen ausgewertet (Dateien `data/extraction/2026101*.json`), 0 abgelehnt.
