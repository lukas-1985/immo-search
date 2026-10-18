---
name: immo-analyse
description: Lauf der Immo-Suche – Angebote von Fredy holen, Merkmale aus Anzeigentexten extrahieren, bewerten und melden. Aufruf `/immo-analyse [profil] [--mode=run|digest] [--listing=<id> --reextract]`.
---

# immo-analyse

Du führst einen Lauf der persönlichen Immobiliensuche aus. Die deterministische Arbeit erledigen die Python-Skripte unter `scripts/`. Deine Aufgabe ist nur, was Urteilsvermögen braucht: **Merkmale aus Freitext extrahieren** (und ab Phase 5 den Digest schreiben).

Alle Befehle laufen im Projektordner mit `uv run python scripts/<name>.py`. Schreibe Dateien **nur** unter `data/`.

## Argumente

| Argument | Bedeutung |
|---|---|
| `profil` (optional) | nur dieses Suchprofil (`config/profiles/<profil>.yaml`), sonst alle aktiven; an jedes Skript als `--profile <profil>` weitergeben |
| `--mode=run` (Standard) | Daten holen, extrahieren, bewerten, Sofortmeldungen |
| `--mode=digest` | wie `run`, danach Digest (ab Phase 5) |
| `--listing=<id> --reextract` | nur dieses Angebot neu auswerten: direkt mit Schritt 3 beginnen und `pending.py --listing <id> --reextract` aufrufen; Schritte 1–2 entfallen |

## Ablauf

1. **Sync:** `uv run python scripts/sync.py` – Exit-Code 1: Lauf abbrechen und den Fehler melden. Exit-Code 2 (Teilfehler): weitermachen, Fehler am Ende nennen.
2. **Regeln:** `uv run python scripts/parse_attrs.py`
3. **Vorlage holen:** `uv run python scripts/pending.py` – liefert JSON mit `angebote` (höchstens 20) und `offen_gesamt`.
   Ist `anzahl` 0, weiter mit Schritt 6.
4. **Extrahieren:** Für jedes Angebot ein Ergebnis nach dem Schema `extraction_schema/<objektart>.json` (Objektart steht in der Vorlage) und den Regeln unten. Alle Ergebnisse in **eine** Datei schreiben:
   `data/extraction/<JJJJMMTT-HHMM>.json` mit dem Inhalt `{"ergebnisse": [ … ]}`.
5. **Speichern:** `uv run python scripts/save.py data/extraction/<datei>.json`
   - Exit-Code 2: Die Ausgabe nennt unter `abgelehnt` die Gründe. Korrigiere **nur** diese Ergebnisse, schreibe sie in eine neue Datei und speichere sie **einmal** erneut. Was dann noch scheitert, wird beim nächsten Lauf wieder vorgelegt.
   - `feld_abgelehnt` bei angenommenen Ergebnissen: einzelne Felder wurden verworfen (z. B. Belegstelle nicht gefunden). Nicht erneut senden, nur im Abschluss erwähnen.
   - Ist `offen_gesamt` größer als die Anzahl der Angebote, Schritte 3–5 wiederholen, höchstens dreimal je Lauf.
6. **Bewerten** (`scripts/score.py`) und **Melden** (`scripts/notify.py`): erst ab Phase 4/5 vorhanden. Fehlt das Skript, diesen Schritt überspringen.
7. **Abschluss:** kurze Zusammenfassung in 3–6 Zeilen: geholt / neu / ausgewertet / abgelehnt / Fehler.

## Regeln für die Extraktion

**Grundsatz: Nur extrahieren, was im Text steht. Nichts raten, nichts aus Erfahrung ergänzen.** Ein Feld, das der Text nicht belegt, wird weggelassen. Ein fehlendes Feld ist kein Fehler, ein falsches schon.

- **Nur Felder aus `gesucht`.** Die Werte unter `bekannt` stammen aus höherrangigen Quellen und werden nicht überschrieben. Nutze sie aber zum Abgleich (z. B. Leerstand ≤ Wohneinheiten).
- **`beschreibung_hash`** unverändert aus der Vorlage übernehmen.
- **`belegstelle`** ist Pflicht: ein **wörtlicher** Ausschnitt aus `text` oder `titel`, keine Umformulierung, höchstens ca. 200 Zeichen. Mehrere Stellen mit ` … ` verbinden. `save` prüft, dass der Ausschnitt im Text steht.
- **`konfidenz`:**
  - `hoch` – ausdrücklich genannt („Jahresnettokaltmiete: 48.000 €“)
  - `mittel` – eindeutig, aber umgerechnet oder aus dem Zusammenhang („4 Wohnungen à ca. 1.000 € kalt im Monat“)
  - `niedrig` – mehrdeutig; lieber weglassen, wenn du zweifelst
- **Zahlen normalisieren:** Euro als Zahl ohne Einheit. Monatsmieten × 12 und dann **`rechenweg`** angeben („3.150 € × 12“). Provision als Anteil (3,57 % → `0.0357`), „provisionsfrei“ → `0`.

### Feldhinweise (Mehrfamilienhaus)

| Feld | Achtung |
|---|---|
| `jahresnettokaltmiete_ist` | **Nur tatsächliche, aktuelle** Mieteinnahmen netto kalt. Nicht: Soll-Miete, „möglich bei Vollvermietung“, Warmmiete, Mietpotenzial. Ist nur eine Warmmiete angegeben → weglassen. |
| `jahresnettokaltmiete_soll` | Miete bei Vollvermietung bzw. nach Anpassung, wenn ausdrücklich genannt |
| `wohneinheiten` / `gewerbeeinheiten` | Gesamtzahl, nicht „davon leer“. Garagen und Stellplätze zählen nicht. |
| `leerstand_einheiten` | nur, wenn ausdrücklich leerstehende Einheiten genannt sind |
| `erbpacht` | `true` bei Erbbaurecht/Erbpacht; `false` nur bei ausdrücklicher Verneinung |
| `denkmalschutz`, `aufgeteilt_weg` | wie `erbpacht`: `false` nur bei ausdrücklicher Verneinung |
| `zustand` | `neuwertig` (Neubau, kernsaniert), `gepflegt`, `renovierungsbeduerftig`, `sanierungsstau` (erheblicher Investitionsbedarf genannt) |
| `sanierungen` | Liste `{bauteil, jahr}`; `jahr: null`, wenn nicht genannt |
| `verhandlungsbasis` | `true` bei „VB“, „Verhandlungsbasis“; `false` bei „Festpreis“ |
| `risiken` | sachliche Kurzbeschreibungen von Auffälligkeiten im Text: Mietrückstände, Feuchtigkeit/Schimmel, Leerstand, Erbpacht, Nießbrauch/Wohnrecht, Sanierungsstau, Rechtsstreit, Zwangsverwaltung, Mietpreisbindung, Altlasten, Schadstoffe (Asbest), Brandschaden, unvollständige Unterlagen. **Keine** allgemeinen Marktrisiken, keine Vermutungen. |

### Beispiel

Vorlage (gekürzt):

```json
{"listing_id": 17, "objektart": "mehrfamilienhaus", "beschreibung_hash": "9f2c…",
 "bekannt": {"wohneinheiten": 4}, "gesucht": ["jahresnettokaltmiete_ist", "leerstand_einheiten", "risiken", "…"],
 "text": "… Die vier Wohnungen erzielen aktuell eine monatliche Nettokaltmiete von insgesamt 3.150 €. Eine Wohnung im DG steht derzeit leer. Im Keller sind Feuchtigkeitsschäden vorhanden. …"}
```

Ergebnis:

```json
{"ergebnisse": [
  {"listing_id": 17, "beschreibung_hash": "9f2c…", "felder": {
    "jahresnettokaltmiete_ist": {"wert": 37800, "konfidenz": "mittel",
      "belegstelle": "erzielen aktuell eine monatliche Nettokaltmiete von insgesamt 3.150 €", "rechenweg": "3.150 € × 12"},
    "leerstand_einheiten": {"wert": 1, "konfidenz": "hoch", "belegstelle": "Eine Wohnung im DG steht derzeit leer"},
    "risiken": {"wert": ["Leerstand einer Wohneinheit", "Feuchtigkeitsschäden im Keller"], "konfidenz": "hoch",
      "belegstelle": "Eine Wohnung im DG steht derzeit leer … Im Keller sind Feuchtigkeitsschäden vorhanden"}
  }}
]}
```

## Was du nicht tust

- Keine Konfiguration ändern, keine Dateien außerhalb von `data/` schreiben, die DB nicht direkt bearbeiten.
- Keine Anbieter kontaktieren, keine Webseiten aufrufen.
- Bei erreichtem Nutzungskontingent oder Zeitnot: nach dem letzten erfolgreichen `save` aufhören. Nicht Gespeichertes wird beim nächsten Lauf wieder vorgelegt.
