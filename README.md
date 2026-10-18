# immo-search

Persönliche Meta-Suche für Kapitalanlage-Immobilien. Konzept und Phasen: [PLAN.md](PLAN.md).

## Stand

- Phase 2 (Kern & Sync): Konfiguration mit Prüfung, eigene DB, Fredy-Client (API / SQLite read-only), `sync` mit `fetch_filter` und Preisverlauf.
- Phase 3 (Extraktion): Schema MFH, Regel-Parser `parse_attrs`, `pending`/`save` mit Schema-, Beleg- und Plausibilitätsprüfung, Skill `immo-analyse`.
- Phase 4 (Scoring & Finanzen): `finance.simulate()`, Kaufpreisempfehlung mit Zinsspanne, KPI-Register, Ausschlusskriterien, Score (gewichtet oder Formel), Ranking. `uv run python scripts/score.py`
- Phase 1 (Fredy auf dem Mini-PC) steht noch aus: Die Feldnamen der Fredy-API sind erst gegen den Quellcode geprüft, nicht gegen ein laufendes System.

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

## Fredy

`docker/fredy/docker-compose.yml` startet Fredy mit festem Image-Tag. In Fredy je Profil und Portal einen Job anlegen; die Job-Namen gehören in `config/profiles/<profil>.yaml` → `fredy.jobs` (oder `job_prefix`).
