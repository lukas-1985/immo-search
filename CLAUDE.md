# CLAUDE.md – Einstieg für neue Sitzungen

Persönliche Meta-Suche für Kapitalanlage-Immobilien (Start: Mehrfamilienhäuser). Fredy (Docker) sammelt Angebote, dieses Projekt filtert, extrahiert (Regeln + Claude-Skill), bewertet und meldet.

**Maßgeblich ist [PLAN.md](PLAN.md).** Stand der Umsetzung: PLAN.md, Abschnitt 13.1. Offene Punkte: Abschnitt 14. Einrichtung des Mini-PCs: [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md).

## Wo wir stehen (zuletzt aktualisiert 18.10.2026)

- **Fertig:** Phasen 2–4: Sync, Extraktion, Scoring mit Kaufpreisempfehlung. 95 Tests grün. Phase 1 ist vorbereitet (Anleitung, `setup.ps1`, `scripts/check_fredy.py`).
- **Phase 1 läuft:** Der Mini-PC (AI-HOME, Lenovo ThinkCentre, Windows 11 direkt auf der Hardware) ist eingerichtet: WSL 2.7.13, Docker Desktop 4.95, uv. Es gibt nur Laufwerk C:. Das Repo liegt unter `C:\E\ai-workspace\immo-search`, Fredys Daten unter `C:\E\docker\fredy` (Standard in `setup.ps1`). Fredy 29.3.0 läuft unter http://localhost:9998.
- **Nächster Schritt:**
  1. **Der Nutzer erledigt selbst:** Fredy-Login, Passwort ändern (danach in `.env`), Analytics ablehnen, Jobs mit Such-URLs anlegen, Platzhalter im Profil füllen. Claude gibt keine Passwörter ein. Anleitung: [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md), Abschnitte 1 und 4–5.
  2. `uv run python scripts/check_fredy.py` ausführen, Bericht und `data/fredy_check/*.json` auswerten, `fredy_client.py` an die echten Felder anpassen, offene Punkte 1–7 in der Tabelle der Anleitung eintragen.
- **Danach:** Phase 5 (Telegram + E-Mail-Digest), Phase 6 (`run.ps1`, Aufgabenplanung, `.claude/settings.json` mit enger Positivliste), dann Phasen 7–8b (Server, MCP, Simulation).

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
| `src/immo/sync.py` | Sync aller Profil-Jobs, `fetch_filter` nur für neue Zuordnungen, Preisverlauf, „entfernt“ |
| `src/immo/filters.py` | `fetch_filter` (Stufe 2) |
| `src/immo/extraction.py` | Schema laden, Belegstellen- und Plausibilitätsprüfung, `store_fields` mit Quellen-Rang |
| `src/immo/parse_attrs.py` | Regel-Parser (Quelle `regel`) |
| `src/immo/claude_io.py` | `pending` / `save` (Schnittstelle zum Skill), `extraction_status` |
| `src/immo/finance.py` | `Annahmen`, `simulate()`, Kaufpreisempfehlung (geschlossene Formel, Zinsspanne) |
| `src/immo/kpis.py` | KPI-Register und Normalisierung |
| `src/immo/scoring.py` | Ausschlusskriterien, Score (gewichtet oder sichere Formel), `run_score`, `ranking` |
| `src/immo/fredy_check.py` | Diagnose gegen das laufende Fredy (Phase 1) |
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
- `GET /api/listings/table` mit `page`, `pageSize`, `sortfield`, `sortdir`, `jobIdFilter`. Die Zeilen stehen unter `result`.

**Tabelle `listings`**
- Spalten u. a. `id, hash, provider, job_id, price, size, rooms, build_year, energy_class, title, image_url, description, address, link, created_at, is_active, latitude, longitude, published_at, price_per_sqm, manually_deleted`.
- Dazu `previous_price`, `price_changed_at`, `market_median_sqm`, `market_sample_size`. Damit ließe sich der KPI `preis_m2_vs_markt` umsetzen.
- Die Portal-IDs sind `immoscout`, `immowelt`, `kleinanzeigen`.

**Ungeprüft, mit `check_fredy.py` am echten System klären**
- Heißen die Felder der API-Antwort genauso wie die DB-Spalten? `listing_from_row` liest snake_case und camelCase.
- Liefert `/table` auch inaktive Angebote?
- In welchem Format kommt `created_at`?
- Gibt es eine Duplikat-Kennung über Portale? Bisher ist keine bekannt, `duplicate_group` = eigene ID.
- Sind die Beschreibungen je Portal vollständig?

## Bekannte Grenzen

- Das Abnahmekriterium von Phase 3 (Ist-Miete ≥ 80 %, erreicht wurden 10/10) ist nur mit **selbst geschriebenen Testanzeigen** geprüft, die Extraktion hat Claude ebenfalls selbst erzeugt. Mit echten Anzeigen erneut messen.
- Ohne `finance.bundesland` im Profil rechnet die Grunderwerbsteuer mit 0 %. Das wird als Hinweis angezeigt.
- Workflow, Notizen, Benachrichtigungen, Server und MCP fehlen noch, die Tabellen dafür gibt es schon.
