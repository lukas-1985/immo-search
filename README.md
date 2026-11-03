# immo-search

Persönliche Meta-Suche für Kapitalanlage-Immobilien. Konzept und Phasen: [PLAN.md](PLAN.md). Aktueller Stand und nächster Schritt: [AGENTS.md](AGENTS.md).

## Stand

- Formatkorrektur (03.11.2026): fehlerhafte KI-Feldwerte werden je Angebot einmal korrigiert; gültige Nachbarergebnisse bleiben gespeichert. Originalantwort von job-7 auf DB-Kopie erfolgreich nachgespielt; 181 Tests grün.

- Korrektur Web-Lauf (03.11.2026): Programmsuche ohne Desktop-PATH ergänzt; echter Test ohne Codex im PATH erfolgreich. 178 Tests grün.

Verifiziert am 03.11.2026: 172 Tests grün, vier echte KI-Testauswertungen ohne Ablehnung und Neuauswertung mit anschließender Bewertung über run.ps1 erfolgreich. Produktiv-DB v3 nach Sicherung migriert, alle 368 Extraktionswerte erhalten; Server auf Port 8710 gestartet. Aufgabenplanung und einwöchige Abnahme bleiben offen.

- 03.11.2026: KI auf Codex mit ChatGPT-Anmeldung umgestellt. Python steuert Extraktion und Speicherung; DB v3 erhält historische Claude-Quellen.

- Phase 2 (Kern & Sync): Konfiguration mit Prüfung, eigene DB, Fredy-Client (API / SQLite read-only), `sync` mit `fetch_filter` und Preisverlauf.
- Phase 3 (Extraktion): Schema MFH, Regel-Parser `parse_attrs`, `pending`/`save` mit Schema-, Beleg- und Plausibilitätsprüfung, Skill `immo-analyse`.
- Phase 4 (Scoring & Finanzen): `finance.simulate()`, Kaufpreisempfehlung mit Zinsspanne, KPI-Register, Ausschlusskriterien, Score (gewichtet oder Formel), Ranking. `uv run python scripts/score.py`
- Phase 1 (Fredy auf dem Mini-PC): läuft, Abschluss nach einigen Tagen Laufzeit. [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md)
- Phasen 7 und 8 (immo-server): Weboberfläche, MCP, Job-Runner, Ranking-Simulation, Konfigurations-Editor. `uv run python scripts/serve.py`, Einrichtung in [docs/SERVER.md](docs/SERVER.md)
- Phase 6 (Automatisierung): Aufgabenplanung für Läufe, Backup und Server-Autostart (`scripts/install_tasks.ps1`), tägliches Backup (`scripts/backup.py`), Health-Prüfung nach jedem Lauf (`scripts/health.py`). Einrichtung in [docs/SERVER.md](docs/SERVER.md), Abschnitt 7; Abnahme (eine Woche unbeaufsichtigt) steht aus.
- Phase 8b (Objekt-Simulation): je Angebot Kauf, Miete, Finanzierung und Kosten ändern, Zielwert-Rückrechnung (Cashflow, Bruttorendite, Nettoanfangsrendite → Kaufpreis, Miete, Zins, Eigenkapital), Szenarien speichern und vergleichen. Button „Simulieren“ in der Detailansicht.
- Phase 8c (Steuern, vereinfacht): Cashflow nach Steuern für Jahr 1 (AfA, Grenzsteuersatz) in Detailansicht und Simulation, KPI `cashflow_nach_steuern`. Score bleibt vor Steuern.
- Offen: Phase 5 (Telegram/Digest), Phase 9 (optional)

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

Einmalig im Windows-Konto für Server und Aufgabenplanung mit `codex login` anmelden. Normaler Einstieg:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File run.ps1
uv run python scripts/extract.py --profile mfh-kl   # nur KI-Extraktion
```

Die folgenden Hilfsbefehle dienen zur Diagnose bzw. zum manuellen Import, nicht zur Steuerung des automatischen Codex-Laufs:

```powershell
uv run python scripts/parse_attrs.py                 # Regeln (Quelle „regel“)
uv run python scripts/pending.py --limit 20          # Vorlage für die KI
uv run python scripts/save.py data/extraction/x.json # KI-Ergebnis prüfen + speichern
```

Im Normalbetrieb: `powershell -File run.ps1`. Nur KI-Extraktion: `uv run python scripts/extract.py`.
Einmalig `codex login` ausführen; `codex login status` prüft die ChatGPT-Anmeldung.
`ki.cli_pfad` kann einen expliziten Programmpfad setzen; bei null werden PATH und die lokalen Windows-Installationsordner durchsucht. Details bei „Codex CLI fehlt“: [SERVER.md, Abschnitt 8.2](docs/SERVER.md#82-codex-wird-im-web-lauf-nicht-gefunden).
`ki` in `config/settings.yaml` steuert Modell (null = Codex-Standard), gesamtes Zeitlimit und Stapelgröße.
Codex liefert strukturierte Daten; Python prüft Schema, Belegstellen und Plausibilität vor der Speicherung.
Erfolgreich ausgewertete Altangebote werden nicht allein wegen des Anbieterwechsels erneut vorgelegt.
Schema und Extraktionsregeln stehen unter `resources/`. Der Skill `immo-analyse` nutzt dieselben Regeln.
Logs: `data/logs/codex-*.log`, Ergebnisse: `data/extraction/codex-*.json`, Rohantworten: `codex-*.antwort.json`. Zuordenbare Formatfehler erhalten einen gezielten Korrekturversuch; Details in [SERVER.md](docs/SERVER.md), Abschnitt 8.3.
Die effektive Modellwahl wird aus dem CLI-Protokoll übernommen und im Lauf sowie je Extraktion gespeichert; fehlt sie dort, wird der konfigurierte Name verwendet (bei null bleibt die Modellspalte leer).

Ohne Fredy ausprobieren (eigene Dev-DB, nie die echte):

```powershell
uv run python scripts/dev_seed.py --db data/dev.db
uv run python scripts/parse_attrs.py --db data/dev.db
uv run python scripts/pending.py --db data/dev.db
uv run python scripts/extract.py --db data/dev.db    # echte Codex-Auswertung, nutzt Kontingent
```

## Fredy (Phase 1)

Schritt-für-Schritt-Anleitung für den Mini-PC: [docs/SETUP-MINIPC.md](docs/SETUP-MINIPC.md).

```powershell
powershell -ExecutionPolicy Bypass -File docker\fredy\setup.ps1   # Fredy starten
uv run python scripts/check_fredy.py                             # Diagnose, liest nur
```

In Fredy je Profil und Portal einen Job anlegen. Die Job-Namen gehören in `config/profiles/<profil>.yaml` → `fredy.jobs` (oder `job_prefix`).
