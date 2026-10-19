# immo-search

Persönliche Meta-Suche für Kapitalanlage-Immobilien. Konzept und Phasen: [PLAN.md](PLAN.md). Aktueller Stand und nächster Schritt: [CLAUDE.md](CLAUDE.md).

## Stand

- Phase 2 (Kern & Sync): Konfiguration mit Prüfung, eigene DB, Fredy-Client (API / SQLite read-only), `sync` mit `fetch_filter` und Preisverlauf.
- Phase 3 (Extraktion): Schema MFH, Regel-Parser `parse_attrs`, `pending`/`save` mit Schema-, Beleg- und Plausibilitätsprüfung, Skill `immo-analyse`.
- Phase 4 (Scoring & Finanzen): `finance.simulate()`, Kaufpreisempfehlung mit Zinsspanne, KPI-Register, Ausschlusskriterien, Score (gewichtet oder Formel), Ranking. `uv run python scripts/score.py`
- Phase 1 (Fredy auf dem Mini-PC): läuft, Abschluss nach einigen Tagen Laufzeit. [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md)
- Phasen 7 und 8 (immo-server): Weboberfläche, MCP, Job-Runner, Ranking-Simulation, Konfigurations-Editor. `uv run python scripts/serve.py`, Einrichtung in [docs/SERVER.md](docs/SERVER.md)
- Phase 6 (Automatisierung): Aufgabenplanung für Läufe, Backup und Server-Autostart (`scripts/install_tasks.ps1`), tägliches Backup (`scripts/backup.py`), Health-Prüfung nach jedem Lauf (`scripts/health.py`). Einrichtung in [docs/SERVER.md](docs/SERVER.md), Abschnitt 7; Abnahme (eine Woche unbeaufsichtigt) steht aus.
- Offen: Phase 5 (Telegram/Digest), Phase 8b (Objekt-Simulation)

## Einrichten

```powershell
uv sync
Copy-Item .env.example .env   # FREDY_PASSWORD eintragen
uv run pytest
```

## Sync

```powershell
uv run python scripts/sync.py                       # alle aktiven Profile
uv run python scripts/sync.py --profile mfh-beispiel
```

Die Ausgabe zeigt je Profil: geholt, neu, aktualisiert, Preisänderungen, entfernt und die Gründe, aus denen der `fetch_filter` Angebote verworfen hat. Dieselben Zahlen stehen in `run_log`.

## Extraktion

```powershell
uv run python scripts/parse_attrs.py                 # Regeln (Quelle „regel“)
uv run python scripts/pending.py --limit 20          # Vorlage für Claude
uv run python scripts/save.py data/extraction/x.json # Claude-Ergebnis prüfen + speichern
```

Im Normalbetrieb ruft der Skill diese Schritte auf: `claude -p "/immo-analyse"`.

Ohne Fredy ausprobieren (eigene Dev-DB, nie die echte):

```powershell
uv run python scripts/dev_seed.py --db data/dev.db
uv run python scripts/parse_attrs.py --db data/dev.db
uv run python scripts/pending.py --db data/dev.db
```

## Fredy (Phase 1)

Schritt-für-Schritt-Anleitung für den Mini-PC: [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md).

```powershell
powershell -ExecutionPolicy Bypass -File docker\fredy\setup.ps1   # Fredy starten
uv run python scripts/check_fredy.py                             # Diagnose, liest nur
```

In Fredy je Profil und Portal einen Job anlegen. Die Job-Namen gehören in `config/profiles/<profil>.yaml` → `fredy.jobs` (oder `job_prefix`).
