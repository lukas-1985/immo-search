# Immo-Suche – Konzept & Umsetzungsplan

> Persönliche Meta-Suche für Kapitalanlage-Immobilien (Start: Mehrfamilienhäuser).
> Stand: 18.10.2026 · Status: Phasen 2–4 (Sync, Extraktion, Scoring & Kaufpreisempfehlung) umgesetzt, Phase 1 (Fredy auf dem Mini-PC) offen.

---

## 0. Kurzfassung

- **Fredy** (Open-Source-Tool, Docker) übernimmt das Einsammeln der Angebote von ImmoScout24, Immowelt (inkl. Immonet), Kleinanzeigen und weiteren Portalen.
- Eine eigene **Analyse-Schicht** liegt darüber und besteht aus zwei Teilen:
  - **Python** erledigt alles Deterministische: Daten holen, filtern, speichern, Score und Finanzkennzahlen berechnen.
  - **Claude** erledigt alles, was Urteilsvermögen braucht: Freitexte auswerten, Auffälligkeiten erkennen, den Digest mit Begründungen schreiben.
- Beides ist in einem **Claude-Skill `immo-analyse`** gebündelt. Ein zeitgesteuerter Claude-Code-Task (ohne Oberfläche) führt ihn auf dem Heimserver aus.
- **Alles ist zentral konfigurierbar**, über ein oder mehrere *Suchprofile* (YAML):
  - Objektart, Region, Fläche, Preis usw.
  - Ausschlusskriterien
  - Score-Formel
  - Finanzannahmen
- **Kaufpreisempfehlung:** Für jedes Angebot wird automatisch der Kaufpreis berechnet, bei dem der monatliche Cashflow neutral ist (Ziel einstellbar). Er wird überall angezeigt: Liste, Detailansicht, Telegram, Digest, MCP.
- **Was-wäre-wenn-Simulation:** alle sinnvollen Parameter (Preis, Miete, Kosten, Finanzierung, Steuern, Entwicklung) je Objekt frei veränderbar, mit sofortiger Neuberechnung, Sensitivitätsanalyse und speicherbaren Szenarien. Dazu eine Simulation des gesamten Rankings.
- **Ausgabe:** Sofortmeldung über Telegram bei Top-Treffern und ein täglicher Digest per E-Mail.
- **Eigener kleiner Server `immo-server`** auf Basis der **eigenen SQLite-DB**. Er stellt zwei Dinge bereit:
  - eine **Web-Oberfläche**: Übersicht, Liste, Detailansicht, Status-Verfolgung, Läufe anstoßen, Konfigurations-Editor, Kaufpreisempfehlung, Objekt- und Ranking-Simulation
  - einen **MCP-Server**: Claude kann suchen, vergleichen und erklären, außerdem Status und Notizen setzen und Läufe anstoßen.
- **Erreichbarkeit:** im Heimnetz und unterwegs über VPN (Tailscale). Nichts ist offen im Internet.

---

## 1. Ziele & Nicht-Ziele

**Ziele**
- Regelmäßig (mehrmals täglich) aktuelle Angebote aus mehreren Portalen an einem Ort sammeln
- Nach eigenen, konfigurierbaren Kriterien filtern und bewerten. Der Standard-Score ist die Bruttorendite.
- Fehlende Merkmale aus Freitexten gewinnen, z. B. Ist-Miete, Einheiten, Erbpacht, Zustand
- Verlauf festhalten: Preissenkungen, Standzeit, Angebot entfernt
- Vorschläge mit Begründung statt einer Flut einzelner Anzeigen
- Gleiche Eingabe ergibt gleichen Score: Bewertungen sind nachvollziehbar und lassen sich wiederholen.
- Für jedes Angebot eine **Kaufpreisempfehlung** auf Basis des Cashflows: Bis zu welchem Preis trägt sich das Objekt selbst?
- Jedes Angebot in einer **Was-wäre-wenn-Simulation** mit allen sinnvollen Parametern durchspielen, als Vorbereitung für Besichtigung, Bankgespräch und Preisverhandlung
- Den eigenen Ablauf vom ersten Sichten bis zum Kauf in einer Oberfläche verfolgen
- Den Datenbestand im Gespräch mit Claude auswerten

**Nicht-Ziele**
- Kein eigenes Scraping, das ist Aufgabe von Fredy
- Keine Weitergabe oder Veröffentlichung der Daten, ausschließlich private Nutzung
- Kein Umgehen von Captchas oder anderen Schutzmechanismen
- Keine automatische Kontaktaufnahme mit Anbietern
- Kein Mehrbenutzer-Betrieb (ein Benutzer) und kein öffentlicher Zugang aus dem Internet

---

## 2. Getroffene Entscheidungen

| Thema | Entscheidung |
|---|---|
| Datenquelle | Fredy (Docker), Version ≥ 28 |
| Portale | ImmoScout24, Immowelt (deckt Immonet ab), Kleinanzeigen, optional OhneMakler, Sparkasse, Immobilien.de u. a. |
| Analyse | Kombination: Claude-Task ruft einen Skill auf, der die Python-Skripte nutzt |
| Datenzugriff | Das Python-Skript holt die Daten **selbst** bei Fredy (HTTP-API, ersatzweise SQLite nur lesend). |
| Oberfläche & MCP | Eigener Server `immo-server` (Python/FastAPI) auf der **eigenen** DB. Fredys Oberfläche und MCP dienen nur noch der Fehlersuche bei Rohdaten. |
| Zugriff | Heimnetz + unterwegs per VPN (Tailscale), **ein** Benutzer mit Login |
| Konfiguration | Die YAML-Dateien bleiben maßgeblich. Die Oberfläche schreibt geprüft und mit Backup in sie zurück. |
| MCP-Schreibrechte | Status & Notizen setzen, Läufe anstoßen. Konfiguration und Extraktion kann Claude **nicht** ändern. |
| Zweck | Kapitalanlage |
| Objektart (Start) | Mehrfamilienhaus, zentral im Suchprofil konfigurierbar |
| Score | Konfigurierbare Formel aus Kennzahlen (KPIs), Standard: Bruttorendite |
| Kaufpreisempfehlung | Preis für neutralen Cashflow (Ziel-Cashflow einstellbar), für jedes Angebot deterministisch in `score` berechnet, geschlossene Formel |
| Simulation | Eine gemeinsame Rechenfunktion `finance.simulate()` für Score, Kaufpreisempfehlung, Oberfläche und MCP. Szenarien je Objekt speicherbar. |
| Region / Budget | Platzhalter im Beispielprofil, legst du selbst fest |
| Benachrichtigung | Telegram (Sofortmeldung) + E-Mail (täglicher Digest), jeweils mit Link zur Detailansicht |
| Betrieb | Mini-PC mit Windows 11, rund um die Uhr. **Nur Fredy läuft in Docker.** Alles Eigene läuft lokal unter Windows: Python-Skripte, `immo-server`, Claude Code, `immo.db`. Siehe Abschnitt 11.1. |

---

## 3. Architektur

```
┌──────────────────────────────── Mini-PC (Windows 11, 24/7) ─────────────────────────────────┐
│                                                                                             │
│  ┌──────── Docker Desktop ────────┐                                                         │
│  │  Fredy                          │                                                        │
│  │  ├─ Jobs je Profil & Portal     │                                                        │
│  │  ├─ Adapter: IS24, Immowelt, KA │                                                        │
│  │  └─ SQLite (/db Volume)         │                                                        │
│  └───────────────┬─────────────────┘                                                        │
│                  │ HTTP-API (bzw. SQLite read-only)                                         │
│  ┌───────────────▼───────────── Kern-Paket „immo“ (Python) ──────────────────────────────┐  │
│  │  config · db · filters · kpis · scoring · finance · fredy_client · notify · jobs       │  │
│  └──────▲───────────────────────────▲─────────────────────────────────▲──────────────────┘  │
│         │                           │                                 │                     │
│  ┌──────┴──────── CLI-Skripte ──┐ ┌─┴──────── immo-server (FastAPI) ─┴────────────────┐    │
│  │ sync · parse_attrs · pending  │ │  Web-UI (Jinja2 + HTMX)   /                        │    │
│  │ save · score · notify         │ │  REST-API                 /api/...                 │    │
│  └──────▲────────────────────────┘ │  MCP (Streamable HTTP)    /mcp                     │    │
│         │                          │  Job-Runner ─► startet claude -p bzw. CLI-Skripte  │    │
│  Skill „immo-analyse“              └──────────────▲──────────────────────▲─────────────┘    │
│         ▲                                         │                      │                  │
│  Windows-Aufgabenplanung ─► claude -p             │ Browser              │ MCP              │
│                                     data/immo.db (SQLite, WAL) ◄─ alle Bausteine            │
└───────────────────────────────────────────────────┼──────────────────────┼──────────────────┘
                                         LAN / Tailscale-VPN       Claude Desktop / Code (LAN/VPN)
```

**Kernprinzip:** Eine einzige Logik in `immo/`. CLI-Skripte, Web-Oberfläche und MCP-Server nutzen **dieselben** Funktionen für Filter, KPIs und Score. Deshalb zeigen Oberfläche, MCP und Digest garantiert dieselben Zahlen.

**Wer macht was?**

| Baustein | Aufgabe | Deterministisch? |
|---|---|---|
| Fredy | Portale abfragen, Duplikate über Portale erkennen, Exposé-Details (IS24) nachladen | – |
| `sync` | Neue und geänderte Angebote holen, Vorfilter anwenden, in eigener DB speichern, Preisverlauf führen | ja |
| `parse_attrs` | Strukturierte Merkmale per Regeln aus der Attributliste bzw. dem Text ziehen (z. B. „Mieteinnahmen pro Jahr“) | ja |
| Claude (Skill) | Lücken aus dem Freitext füllen (festes Schema), Risiken erkennen, Digest formulieren | nein, Ergebnis wird **einmalig gespeichert** |
| `save` | Claude-Extraktion gegen das JSON-Schema prüfen und speichern | ja |
| `score` | Ausschlusskriterien, KPIs, Score, Finanzierung, Ranking | ja |
| `notify` | Telegram und E-Mail versenden | ja |
| `immo-server` | Oberfläche, REST-API, MCP, Job-Runner, Konfigurations-Editor | ja |

---

## 4. Ablauf eines Laufs

```
/immo-analyse [profil] [--mode=run|digest] [--listing=<id> --reextract]

1. sync         Angebote der Profil-Jobs von Fredy holen
                → fetch_filter anwenden (Ort, Fläche, Preis, …)
                → neue Angebote anlegen, Änderungen (Preis, Status) als Historie
2. parse_attrs  Regelbasierte Extraktion (Attributlisten, eindeutige Muster)
3. pending      Unbewertete Angebote kompakt ausgeben (nur relevante Felder + Text)
4. Claude       Merkmale nach extraction_schema extrahieren, Risiken markieren
5. save         Validieren & speichern (Quelle je Feld: portal | regel | claude | schätzung)
6. score        Hard-Filter → KPIs → Score → Ranking (alle Profile, auch Bestand neu)
7a. mode=run    notify: Telegram für neue Treffer ≥ Schwellwert
7b. mode=digest Claude schreibt Digest (Top-N, Pro/Contra, Preisänderungen,
                Warnungen, Status-Übersicht) → notify versendet E-Mail
```

**Auslöser:**

| Auslöser | Modus |
|---|---|
| Windows-Aufgabenplanung | `run` alle 3 Stunden zwischen 7 und 22 Uhr, `digest` täglich um 7:30 Uhr (beides in `settings.yaml` → `schedule` einstellbar) |
| Oberfläche („Jetzt ausführen“, „Neu auswerten“, „Digest senden“) | über den Job-Runner des Servers |
| MCP (`start_run`, `reextract_listing`, `send_digest_now`) | über denselben Job-Runner |

**Sperre gegen parallele Läufe:** Zeitplan, Oberfläche und MCP teilen sich eine Sperre (Lock-Datei + Tabelle `job`). Es läuft immer nur **ein** Lauf, weitere werden eingereiht.

**Wichtig:** Claude wertet jedes Angebot nur **einmal** aus.
- Ändert sich die Gewichtung oder Formel, rechnet `score` alle Angebote neu (Sekunden, ohne Claude). Das passiert auch automatisch nach dem Speichern der Konfiguration in der Oberfläche.
- Eine erneute Auswertung durch Claude gibt es nur, wenn sich die Beschreibung ändert (Hash-Vergleich) oder du sie ausdrücklich anforderst (Oberfläche, MCP oder `--reextract`).

---

## 5. Konfiguration (zentral)

### 5.1 Aufbau

```
config/
  settings.yaml            ← global: Fredy-Zugang, Server, Benachrichtigungen, Zeitpläne, Steuern
  profiles/
    mfh-beispiel.yaml      ← ein Suchprofil = Objektart + Region + Filter + Score + Finanzen
    etw-beispiel.yaml      ← weitere Profile jederzeit möglich (aktiv/inaktiv)
  .history/                ← automatische Backups vor jeder Änderung über die Oberfläche
.env                       ← Geheimnisse (Tokens, Passwörter) – nicht im Git
```

**Warum Profile statt Skill-Parametern?**
- Die Objektart allein reicht nicht. Zu ihr gehören immer passende Filter, KPIs und Finanzannahmen. Für ein MFH sind z. B. die Einheiten wichtig, für eine ETW das Hausgeld.
- Ein Profil bündelt all das an **einer** Stelle, liegt versioniert in Git und lässt sich auch ohne Claude nutzen.
- Der **Skill-Parameter wählt nur das Profil aus:** `/immo-analyse mfh-beispiel`. Ohne Parameter laufen alle aktiven Profile.

**Prüfung:** Ein Pydantic-Modell beschreibt die zulässige Struktur. CLI, Server und Konfigurations-Editor prüfen dagegen. Eine fehlerhafte Konfiguration wird nie gespeichert oder verwendet.

### 5.2 Drei Filterstufen

| Stufe | Wo | Worauf | Zweck |
|---|---|---|---|
| 1. Portalsuche | Fredy-Job (Such-URL des Portals) | was das Portal filtern kann | Grobe Vorauswahl, wenig Last |
| 2. **`fetch_filter`** | `sync`, **vor** dem Speichern | Felder, die Fredy liefert: Ort/PLZ/Umkreis, Preis, Fläche, Zimmer, Baujahr, Portal | Genauer eingrenzen, als es die Portale können. Spart Claude-Aufwand. |
| 3. `hard_filter` | `score`, nach der Extraktion | alle Felder, auch die aus dem Freitext (Erbpacht, Einheiten, Ist-Miete, …) | Ausschlusskriterien |

Angebote, die an Stufe 2 scheitern, werden **gar nicht** gespeichert. Für die Diagnose zählt das Skript sie nur mit. Angebote, die an Stufe 3 scheitern, bleiben mit Ausschlussgrund in der DB. Sie erscheinen nicht im Ranking, sind in der Oberfläche aber über den Filter „Ausgeschlossene anzeigen“ sichtbar.

> **Hinweis:** `sync` liest bei jedem Lauf den gesamten Bestand der Profil-Jobs aus Fredy (wenige hundert Angebote, lokal). Bekannte Angebote werden immer aktualisiert, neue gegen den aktuellen `fetch_filter` geprüft. Wird der Filter *gelockert*, kommen früher verworfene Angebote deshalb beim nächsten Lauf automatisch hinzu. Ein eigener Modus `--full` ist nicht nötig.
>
> Ein Angebot, das schon über ein anderes Profil bekannt ist, wird einem weiteren Profil nur zugeordnet, wenn es dessen `fetch_filter` besteht. Als „entfernt“ gilt es erst, wenn **kein** erfolgreich abgerufener Job es mehr liefert.

### 5.3 Beispielprofil `config/profiles/mfh-beispiel.yaml`

```yaml
id: mfh-beispiel
name: "MFH Region X (Beispiel)"
active: true
objektart: mehrfamilienhaus          # steuert Extraktionsschema & Default-KPIs

# Stufe 1 – zugehörige Fredy-Jobs (Such-URLs werden in Fredy gepflegt)
fredy:
  jobs: ["MFH Region X – IS24", "MFH Region X – Immowelt", "MFH Region X – Kleinanzeigen"]
  # alternativ: job_prefix: "MFH Region X"

# Stufe 2 – Vorfilter beim Datenholen (nur Felder, die Fredy liefert)
fetch_filter:
  location:
    plz_prefix: ["XX"]               # PLATZHALTER
    orte: ["Ort A", "Ort B"]         # PLATZHALTER
    umkreis: { lat: 0.0, lon: 0.0, km: 30 }   # PLATZHALTER, optional
  preis:       { min: 0, max: 0 }    # PLATZHALTER (€)
  wohnflaeche: { min: 0 }            # PLATZHALTER (m²)
  baujahr:     { min: null, max: null }
  providers:   [immoscout, immowelt, kleinanzeigen]
  exclude_keywords: ["Zwangsversteigerung", "Tausch"]   # im Titel

# Stufe 3 – Ausschlusskriterien (auch extrahierte Felder)
hard_filter:
  - { field: erbpacht,        op: "==", value: false, on_missing: keep }
  - { field: wohneinheiten,   op: ">=", value: 3,     on_missing: keep }
  - { field: denkmalschutz,   op: "==", value: false, on_missing: keep }
  - { field: bauprojekt,      op: "==", value: false, on_missing: keep }
  - { field: bruttorendite,   op: ">=", value: 0.04,  on_missing: keep }
  # on_missing: keep = behalten & als „unvollständig“ markieren | drop = ausschließen

# Score – konfigurierbare Formel aus KPIs
scoring:
  kpis:
    bruttorendite:
      weight: 1.0
      normalize: { type: linear, min: 0.04, max: 0.08 }   # 4 % → 0 Pkt, 8 % → 100 Pkt
      on_missing: estimate    # estimate | zero | exclude
  # Weitere KPIs (Beispiele, deaktiviert):
  #  faktor:               { weight: 0,   normalize: { type: linear, min: 25, max: 12 } }
  #  cashflow_monat:       { weight: 0,   normalize: { type: linear, min: -500, max: 1000 } }
  #  mietpotenzial:        { weight: 0,   normalize: { type: linear, min: 0, max: 0.3 } }
  #  preis_m2_vs_markt:    { weight: 0,   normalize: { type: linear, min: 0.3, max: -0.3 } }
  # Optional: freie Formel statt gewichteter Summe (sicherer Ausdrucks-Evaluator)
  # formula: "0.7 * bruttorendite_n + 0.3 * mietpotenzial_n"
  alert_threshold: 75          # Telegram-Sofortmeldung ab diesem Score
  digest_top_n: 10

# Finanzannahmen (überschreiben Defaults aus settings.yaml)
finance:
  bundesland: XX               # PLATZHALTER → Grunderwerbsteuer aus Tabelle
  eigenkapital: 0              # PLATZHALTER (€) oder "nebenkosten" (EK = Kaufnebenkosten, Kaufpreis voll finanziert)
  zins: 0.038
  tilgung: 0.02
  notar_grundbuch: 0.02
  makler_default: 0.0357       # wenn nicht aus Anzeige bekannt
  bewirtschaftung_quote: 0.20  # nicht umlagefähige Kosten + Rücklage, Anteil der Kaltmiete
  instandhaltung_eur_m2_jahr: 0  # optional zusätzlich zur Quote (€/m² Wohnfläche/Jahr)
  sanierung_sofort: 0          # Anfangsinvestition nach Kauf (€), wird mitfinanziert
  miete_schaetzung_eur_m2: 0   # PLATZHALTER – für on_missing: estimate (als Schätzung markiert)

# Kaufpreisempfehlung (siehe 5.6)
kaufpreisempfehlung:
  ziel_cashflow_monat: 0       # 0 = neutraler Cashflow; z. B. 200 = 200 € Überschuss/Monat
  tilgung_einrechnen: true     # true: Cashflow nach Zins UND Tilgung (konservativ) | false: nur Zins
```

### 5.4 KPI-Register (in `immo/kpis.py`)

Jede Kennzahl ist eine benannte Funktion. Sie liefert `(wert, qualität)`, wobei die Qualität angibt, ob der Wert *exakt* ist, aus einer *Extraktion* stammt oder *geschätzt* ist. Neue KPIs werden einmal im Code ergänzt und sind danach per Konfiguration nutzbar. Sie erscheinen dann automatisch auch im Konfigurations-Editor und in beiden Simulationen.

| KPI | Formel | Benötigt |
|---|---|---|
| `bruttorendite` | Jahresnettokaltmiete (Ist) / Kaufpreis | Ist-Miete (Extraktion oder Schätzung) |
| `faktor` | Kaufpreis / Jahresnettokaltmiete | dito |
| `nettoanfangsrendite` | (Jahresmiete − Bewirtschaftung) / (Kaufpreis + Nebenkosten) | + Finanzannahmen |
| `cashflow_monat` | (Miete − Bewirtschaftung − Zins − Tilgung) / 12, Formel siehe 5.6. Mit `tilgung_einrechnen: false` ohne Tilgung, damit Cashflow und Kaufpreisempfehlung dieselbe Definition haben. | + Finanzierung |
| `preis_m2` | Kaufpreis / Wohnfläche | Fläche |
| `mietpotenzial` | (Marktmiete − Ist-Miete) / Ist-Miete | Marktmiete (Konfiguration/Mietspiegel) |
| `preis_m2_vs_markt` | Preis/m² ggü. lokalem Median (Fredy-Benchmark) | Fredy-Daten |
| `kaufpreisempfehlung` | Kaufpreis, bei dem `cashflow_monat` = Ziel-Cashflow, siehe 5.6 | + Finanzierung |
| `preisabstand` | (Angebotspreis − Kaufpreisempfehlung) / Angebotspreis. Positiv = Angebot liegt darüber. | dito |

`preisabstand` kann wie jede KPI in Score, Ausschlusskriterien und Filtern verwendet werden, z. B. „höchstens 10 % über der Empfehlung“.

**Normalisierung:**
- Jede KPI wird auf 0–100 Punkte abgebildet (`linear`, später auch `stufen` oder `ziel`).
- Der Score ist die gewichtete Summe der Punkte geteilt durch die Summe der Gewichte, bleibt also bei 0–100. Alternativ gilt die freie `formula` (Namen: `<kpi>` = Rohwert, `<kpi>_n` = Punkte; erlaubt sind + − × ÷, `min`, `max`, `abs`).
- `on_missing` je KPI, wenn der Wert fehlt oder nur geschätzt ist:
  - `estimate`: Schätzung verwenden. Gibt es keine, zählt die KPI 0 Punkte.
  - `zero`: 0 Punkte.
  - `exclude`: Die KPI fällt für dieses Angebot aus der Summe.
  
  Das Angebot wird in allen drei Fällen als „unvollständig“ markiert.
- `mietpotenzial` braucht `finance.marktmiete_eur_m2` im Profil. `preis_m2_vs_markt` folgt, sobald `sync` Fredys Markt-Benchmark übernimmt.
- Jedes Ergebnis speichert, welche KPIs eingeflossen sind und welche davon geschätzt wurden. Im Digest und in der Detailansicht ist das sichtbar.

### 5.5 Globale Einstellungen `config/settings.yaml` (Auszug)

```yaml
fredy:
  base_url: "http://localhost:9998"
  access: api            # api | sqlite
  sqlite_path: "D:/docker/fredy/db/listings.db"   # nur für access: sqlite (read-only)
server:
  bind: ["127.0.0.1", "192.168.x.x", "100.x.x.x"]   # localhost, LAN, Tailscale – PLATZHALTER
  port: 8710
  public_base_url: "http://immo-minipc:8710"     # für Links in Telegram/Digest (Tailscale-Name)
  mcp:
    enabled: true
    write_tools: [set_status, add_note, start_run, reextract_listing, send_digest_now]
notify:
  telegram: { enabled: true }            # Token/Chat-ID aus .env
  email:    { enabled: true, to: "<deine Adresse>" }   # SMTP-Zugang aus .env
schedule:
  run:    { every_hours: 3, from: "07:00", to: "22:00" }
  digest: { at: "07:30" }
workflow:                # Status-Workflow (siehe Abschnitt 6), Reihenfolge = Ablauf
  status: [neu, gesichtet, interessant, angefragt, besichtigt, angebot_abgegeben, gekauft]
  end_status: [abgelehnt, verworfen]   # jederzeit erreichbar, blenden das Angebot aus
  wieder_interessant_preissenkung: 0.10   # Hinweis bei verworfenem Angebot ab −10 %
grunderwerbsteuer:       # Tabelle je Bundesland, regelmäßig prüfen
  BY: 0.035
  NW: 0.065
  # …
steuern:                 # nur für die Simulation „Cashflow nach Steuern“ (vereinfacht)
  grenzsteuersatz: 0.42  # PLATZHALTER, persönlicher Satz inkl. Soli
  gebaeudeanteil: 0.75   # Anteil Gebäude am Kaufpreis (Rest Grund & Boden, nicht abschreibbar)
  afa_satz: auto         # auto = nach Baujahr (2,5 % vor 1925, 2 % bis 2022, 3 % ab 2023) oder fester Wert
```

### 5.6 Kaufpreisempfehlung (Preis für neutralen Cashflow)

Für jedes Angebot rechnet `score` den Kaufpreis aus, bei dem sich das Objekt mit den Finanzannahmen des Profils **selbst trägt**. Die Funktion liegt in `immo/finance.py` und ist deterministisch.

**Größen:**

| Zeichen | Bedeutung | Quelle |
|---|---|---|
| M | Jahresnettokaltmiete (Ist) | Extraktion bzw. Schätzung |
| B | Bewirtschaftung = `bewirtschaftung_quote` · M + `instandhaltung_eur_m2_jahr` · Wohnfläche | Profil |
| n | Kaufnebenkosten-Quote = Grunderwerbsteuer + Notar/Grundbuch + Makler | Profil, Makler aus Anzeige oder `makler_default` |
| S | Sanierung sofort | Profil (Standard 0) |
| EK | Eigenkapital | Profil |
| k | Kapitaldienst-Satz = Zins + Tilgung (bzw. nur Zins, wenn `tilgung_einrechnen: false`) | Profil |
| C | Ziel-Cashflow pro Monat | Profil (Standard 0) |

**Rechnung:**

```
Darlehen      D  = P · (1 + n) + S − EK
Cashflow/Jahr CF = M − B − k · D
Empfehlung    P* = ( (M − B − 12·C) / k + EK − S ) / (1 + n)
```

**Sonderfälle und Kennzeichnung:**
- Ist M − B − 12·C ≤ 0, lässt sich das Ziel bei keinem Preis erreichen, auch nicht ohne Kredit. Das Angebot wird mit „Ziel-Cashflow nicht erreichbar“ markiert.
- Die Qualität der Empfehlung folgt der Miete: exakt, extrahiert oder **geschätzt**. Eine geschätzte Empfehlung ist überall deutlich gekennzeichnet.
- Fehlt die Miete und ist keine Schätzung konfiguriert, gibt es keine Empfehlung, nur den Hinweis „Miete fehlt“.
- Gespeichert werden P*, `preisabstand` und der Rechenweg (alle Eingangswerte) in `score.kpis_json`. So ist jede Empfehlung nachvollziehbar.
- Zusätzlich wird die **Zinsempfindlichkeit** gespeichert: P* bei Zins −0,5 und +0,5 Prozentpunkte. Das zeigt, wie stark die Empfehlung von der Zinsannahme abhängt.

**Hinweis:** Die Empfehlung ist eine Rechengröße aus deinen Annahmen, keine Marktbewertung. Sie sagt, bis zu welchem Preis das Objekt zu deinen Bedingungen passt, nicht was es wert ist. Den Marktvergleich liefert `preis_m2_vs_markt`.

---

## 6. Datenmodell (eigene DB `data/immo.db`, SQLite)

Getrennt von Fredys DB. Fredy wird nie beschrieben. Die DB läuft im **WAL-Modus** mit `busy_timeout`, damit Oberfläche und MCP lesen können, während ein Lauf schreibt.

| Tabelle | Inhalt |
|---|---|
| `listing` | `id`, `fredy_id`, `provider`, `url`, `titel`, `adresse`, `plz`, `ort`, `lat/lon`, `preis`, `flaeche`, `zimmer`, `baujahr`, `energieklasse`, `beschreibung`, `beschreibung_hash`, `bilder`, `first_seen`, `last_seen`, `status_portal` (aktiv/entfernt), `duplicate_group` |
| `listing_profile` | Zuordnung Angebot ↔ Profil (ein Angebot kann zu mehreren Profilen passen) |
| `price_history` | `listing_id`, `datum`, `preis` |
| `extraction` | `listing_id`, `feld`, `wert`, `quelle` (portal/regel/claude/schätzung), `konfidenz`, `belegstelle` (Textausschnitt), `schema_version`, `extracted_at` |
| `extraction_status` | Stand der Claude-Auswertung je Angebot: `beschreibung_hash`, `schema_version`, `status` (ok/fehler), `versuche`, `letzter_fehler`. Grundlage für „nur einmal auswerten“. |
| `score` | `listing_id`, `profile_id`, `score`, `kpis_json` (inkl. Kaufpreisempfehlung, Rechenweg, Zinsspanne), `kaufpreisempfehlung`, `preisabstand` (eigene Spalten für Sortierung und Filter), `hard_filter_result`, `ausschlussgrund`, `config_hash`, `scored_at` |
| `scenario` | Gespeicherte Simulations-Szenarien: `id`, `listing_id`, `profile_id`, `name`, `annahmen_json` (nur die geänderten Parameter), `ergebnis_json` (Stand beim Speichern), `created_at`, `updated_at` |
| `workflow` | Dein Bearbeitungsstand je Angebot (Duplikatgruppe): `status`, `updated_at`, `updated_by` (ui/mcp) |
| `workflow_history` | Jeder Statuswechsel mit Zeitpunkt, Quelle (ui/mcp) und optionaler Notiz |
| `note` | Freie Notizen je Angebot (`text`, `created_at`, `quelle` ui/mcp) |
| `job` | Angestoßene Läufe: `typ`, `parameter`, `ausgelöst_von` (zeitplan/ui/mcp), `status` (wartend/läuft/fertig/fehler), `start`, `ende`, `log_pfad` |
| `notification` | Was wann über welchen Kanal gemeldet wurde, damit nichts doppelt gemeldet wird |
| `run_log` | Kennzahlen je Lauf: Anzahl geholt, gefiltert, extrahiert, gemeldet, Fehler |
| `config_change` | Änderungen der Konfiguration über die Oberfläche: Datei, Diff, Backup-Pfad, Zeitpunkt |

**Status-Workflow** (in `settings.yaml` → `workflow` anpassbar, siehe 5.5):

```
neu → gesichtet → interessant → angefragt → besichtigt → angebot_abgegeben → gekauft
                       └──────────────┴──────────┴──────────────┴─────→ abgelehnt / verworfen
```

- Der Status hängt an der **Duplikatgruppe**. Ein Objekt, das auf drei Portalen inseriert ist, hat also nur einen Status.
- Angebote mit `abgelehnt` oder `verworfen` erscheinen nicht mehr in Digest und Telegram. Das Ranking blendet sie standardmäßig aus.
- Sinkt der Preis eines verworfenen Angebots deutlich, gibt es optional einen Hinweis („wieder interessant?“).

---

## 7. Extraktion aus dem Freitext

**Schema:** `extraction_schema.json`, je Objektart. Für Mehrfamilienhäuser:

| Feld | Typ | Beispiel |
|---|---|---|
| `wohneinheiten`, `gewerbeeinheiten` | int | 6, 1 |
| `jahresnettokaltmiete_ist` | € | 48.000 |
| `jahresnettokaltmiete_soll` | € | 54.000 |
| `leerstand_einheiten` | int | 1 |
| `provision` | % / „provisionsfrei“ | 3,57 % |
| `grundstueck_m2` | int | 820 |
| `erbpacht`, `denkmalschutz`, `aufgeteilt_weg` | bool | false |
| `bauprojekt` | bool (true = Fertighaus-/Ausbauhaus-Angebot, kein Bestand) | false |
| `heizungsart`, `heizung_baujahr` | text, int | Gas, 2012 |
| `sanierungen` | Liste {Bauteil, Jahr} | Dach 2018, Fenster 2010 |
| `zustand` | Aufzählung | gepflegt / renovierungsbedürftig / Sanierungsstau |
| `risiken` | Liste | „Mietrückstände erwähnt“, „Feuchtigkeit Keller“ |
| `verhandlungsbasis` | bool | true |

**Regeln für Claude (in SKILL.md):**
- Nur extrahieren, was im Text steht. Zu jedem Wert gehört die Belegstelle, nichts wird geraten.
- Zahlen werden normalisiert: Monatsmieten werden auf das Jahr hochgerechnet, und der Rechenweg wird festgehalten.
- Unsicherheit wird als `konfidenz` (hoch/mittel/niedrig) angegeben.
- Die Ausgabe ist nur JSON im Schema-Format. `save` lehnt ungültige Einträge ab, und das Angebot wird beim nächsten Lauf erneut vorgelegt (höchstens 3 Versuche, danach erst wieder bei geändertem Text oder auf Anforderung).

**Prüfungen in `save`** (gelten auch für Regelwerte):
1. JSON-Schema der Objektart. Ein Verstoß lehnt das ganze Ergebnis ab.
2. Die Belegstelle muss wörtlich in Titel oder Beschreibung stehen (Leerraum und Anführungszeichen egal, Teile mit „…“ getrennt). Sonst wird nur dieses Feld verworfen.
3. Plausibilität, z. B. Jahresmiete zwischen 1 % und 25 % des Kaufpreises (fängt Monats-/Jahresverwechslungen ab), Leerstand ≤ Einheiten.
4. Hat sich die Beschreibung seit `pending` geändert, wird das Ergebnis abgelehnt.

**Regelbasierter Parser:** nur eindeutige Bezeichnungen („Mieteinnahmen pro Jahr: …“), widersprüchliche Treffer ergeben keinen Wert. Da Regelwerte Vorrang vor Claude haben, gilt: lieber nichts finden als falsch finden.

**Reihenfolge der Quellen:**
1. Strukturierte Portaldaten
2. Regelbasierter Parser
3. Claude
4. Schätzung aus der Konfiguration

Höhere Stufen werden nicht überschrieben.

---

## 8. Benachrichtigungen

| Kanal | Auslöser | Inhalt | Erzeugt von |
|---|---|---|---|
| Telegram | Modus `run`, neuer Treffer mit Score ≥ `alert_threshold` oder deutliche Preissenkung bei einem Top-Angebot | Kurzinfo: Titel, Ort, Preis, **Kaufpreisempfehlung mit Abstand**, Bruttorendite, Score, **Link zur Detailansicht** + Portal-Link | `notify` (Vorlage, ohne Claude) |
| E-Mail | Modus `digest`, täglich oder per „Digest jetzt senden“ | Top-N je Profil mit Pro/Contra und Kaufpreisempfehlung (Abstand, Verhandlungsbasis laut Anzeige), neue Angebote, Preissenkungen, entfernte Favoriten, unvollständige Kandidaten („Miete fehlt – nachfragen“), offene Vorgänge je Status | Text von Claude, Versand per `notify` (SMTP) |

- **Links** zeigen auf `public_base_url` (Tailscale-Name). Sie funktionieren deshalb zu Hause und unterwegs, wenn das VPN aktiv ist.
- **Fredys eigene Benachrichtigungen** deaktivieren, sonst kommen Meldungen doppelt.
- **Fehlermeldungen** (Fredy nicht erreichbar, Portal liefert seit X Tagen nichts, Lauf fehlgeschlagen) gehen ebenfalls per Telegram.

---

## 9. Skill & Claude-Task

### 9.1 Skill-Struktur (Projekt-Skill)

```
.claude/skills/immo-analyse/
  SKILL.md                 ← Ablauf, Regeln, Ausgabeformat Digest
  extraction_schema/
    mehrfamilienhaus.json
  templates/
    digest.md              ← Struktur des Digests
```

Die Logik liegt im Paket `immo/`, die CLI-Einstiege unter `scripts/`, die Konfiguration unter `config/`. Der Skill verweist darauf. So lassen sich die Skripte auch ohne Claude ausführen und testen.

### 9.2 Aufruf

```bash
claude -p "/immo-analyse --mode=run"
```

```bash
claude -p "/immo-analyse mfh-beispiel --mode=digest"
```

- **Zeitsteuerung:** Windows-Aufgabenplanung auf dem Mini-PC. Ein Wrapper-Skript `run.ps1` übernimmt Logging, Zeitlimit und eine Fehlermeldung per Telegram, wenn der Lauf scheitert. Der Job-Runner des Servers nutzt **denselben** Wrapper.
- **Berechtigungen:** Die Projekt-Einstellungen (`.claude/settings.json`) erlauben nur die nötigen Werkzeuge: Lesen, `python scripts/*.py`, kein Schreiben außerhalb von `data/`. So kann der unbeaufsichtigte Task nichts Unerwartetes tun.
- **Anmeldung:** Claude Code läuft mit deinem Abo und nutzt **standardmäßig die normale Anmeldung des Benutzerkontos** (siehe 11.1). Das gilt für Zeitplan und Job-Runner gleichermaßen. Ein langlebiges Token (`claude setup-token`, als `CLAUDE_CODE_OAUTH_TOKEN` in `.env`) ist nur die **Rückfallebene**: falls die normale Anmeldung im unbeaufsichtigten Betrieb abläuft oder Läufe unter einem eigenen Konto „immo“ laufen. In Phase 1 prüfen.
- **Kontingent:** Etwa 5–30 neue Angebote pro Tag mit je einer kompakten Auswertung plus einem Digest. Das sollte gut in das Nutzungskontingent passen. Überwachung über `run_log`.

---

## 10. `immo-server`: Web-Oberfläche & MCP-Server

Ein einziger Python-Prozess (FastAPI + Uvicorn) stellt Oberfläche, REST-API und MCP bereit. Er arbeitet **nur auf `data/immo.db`** und den Konfigurationsdateien und spricht nie direkt mit Fredy. Neue Daten kommen ausschließlich über Läufe.

### 10.1 Technik

| Thema | Wahl | Begründung |
|---|---|---|
| Server | FastAPI + Uvicorn | Schlank, gemeinsame Python-Logik mit den Skripten |
| Oberfläche | Server-gerenderte Seiten (Jinja2) + **HTMX**, kleines CSS-Framework (z. B. Pico.css), Chart.js für den Preisverlauf | Kein Build-Schritt, kein separates Frontend-Projekt, schnell und wartungsarm, funktioniert auf dem Handy |
| MCP | Offizielles MCP-Python-SDK (FastMCP), Transport **Streamable HTTP** unter `/mcp`, im selben Prozess | Ein Dienst, eine Anmeldung, dieselbe Logik |
| Konfigurations-Editor | `ruamel.yaml` (Kommentare und Reihenfolge bleiben erhalten) + Pydantic-Prüfung | YAML bleibt von Hand lesbar und Git-freundlich |
| Job-Runner | Hintergrund-Warteschlange im Server, ein Lauf gleichzeitig, startet `run.ps1` | Gleicher Ablauf wie die Zeitsteuerung |

### 10.2 Ansichten der Oberfläche

**1. Übersicht (Start)**
- Kacheln: neu heute bzw. diese Woche, Top-Score, Preissenkungen, offene Vorgänge je Status
- Zustand: letzter Lauf, nächster geplanter Lauf, Zustand je Portal (letztes Angebot vor X Tagen)
- Kurzliste „Top 10 je Profil“

**2. Liste aller Angebote**
- Tabelle mit Spalten wie Score, Bruttorendite, Preis, **Kaufpreisempfehlung** und **Preisabstand** (farbig: grün = Angebot unter der Empfehlung, rot = darüber), Einheiten, Ort, Portal(e), Standzeit, Preisänderung, Status und Vollständigkeit
- Filter nach Profil, Status, Score-Bereich, Ort/PLZ, Portal, „nur unvollständige“ und „Ausgeschlossene anzeigen“
- Sortierbar und durchsuchbar (Volltext in Titel und Beschreibung)
- Seitenweise Anzeige, Filter bleiben in der URL erhalten (Lesezeichen möglich)

**3. Detailansicht**
- Stammdaten und Bilder, Links zu allen Portalen der Duplikatgruppe
- **Score-Aufschlüsselung:** jede KPI mit Rohwert, Punkten, Gewicht und Qualität (exakt/extrahiert/geschätzt), Ergebnis der Ausschlusskriterien
- **Extrahierte Merkmale:** Wert, Quelle, Konfidenz, Belegstelle (Textstelle hervorgehoben)
- **Kaufpreisempfehlung** prominent oben neben dem Angebotspreis: Empfehlung, Abstand in € und %, Qualität (exakt/extrahiert/geschätzt), Spanne bei Zins ±0,5 Pp. Aufklappbar der Rechenweg mit allen Eingangswerten.
- Finanzrechnung: Kaufnebenkosten, Gesamtinvestition, Rate, Cashflow
- Preisverlauf als Diagramm (mit Linie der Kaufpreisempfehlung), Standzeit
- Risiken und Pro/Contra aus der Claude-Auswertung
- **Status setzen** mit optionaler Notiz, Verlauf der Statuswechsel
- Button „Neu auswerten (Claude)“, Button **„Simulieren“** (öffnet die Objekt-Simulation mit den Werten dieses Angebots)

**4. Was-wäre-wenn: Objekt-Simulation**

Ein Angebot mit beliebigen Annahmen durchrechnen. Ausgangspunkt sind immer die aktuellen Werte des Angebots und die Finanzannahmen seines Profils. Jeder Parameter lässt sich per Regler oder Feld ändern, geänderte Werte sind markiert und einzeln zurücksetzbar. Die Ergebnisse werden **sofort** neu berechnet (HTMX, serverseitig mit `finance.simulate()`).

*Parameter:*

| Gruppe | Parameter |
|---|---|
| Kauf | Kaufpreis, Makler (%), Grunderwerbsteuer (%), Notar/Grundbuch (%), Sanierung sofort (€) |
| Einnahmen | Ist-Miete (€/Jahr oder €/m²), Zielmiete nach Neuvermietung/Mieterhöhung, Zeitpunkt der Anpassung, Leerstand (Einheiten oder %), Mietausfallwagnis (%) |
| Kosten | Bewirtschaftungsquote, Instandhaltung (€/m²/Jahr), Verwaltung (€/Einheit/Monat), Kostensteigerung (%/Jahr) |
| Finanzierung | Eigenkapital, Zins, Tilgung, Zinsbindung (Jahre), Anschlusszins, optional zweites Darlehen (z. B. KfW) mit eigenem Zins und eigener Tilgung |
| Steuern (vereinfacht) | Grenzsteuersatz, Gebäudeanteil, AfA-Satz |
| Entwicklung | Haltedauer (Jahre), Mietsteigerung (%/Jahr), Wertsteigerung (%/Jahr), Verkaufsnebenkosten (%) |
| Ziel | Ziel-Cashflow pro Monat (für die Kaufpreisempfehlung) |

*Ergebnisse:*
- **Kennzahlen** wie in der Detailansicht: Bruttorendite, Faktor, Nettoanfangsrendite, Cashflow vor und nach Steuern, Score. Jeweils mit Abweichung zum Ausgangswert.
- **Kaufpreisempfehlung** für die aktuellen Annahmen
- **Break-even-Werte:** höchster Zins, niedrigste Miete und höchster Leerstand, bei denen der Cashflow noch neutral ist
- **Verlauf über die Haltedauer** (Tabelle und Diagramm): Miete, Kosten, Zins, Tilgung, Restschuld, Cashflow, kumulierter Cashflow, Objektwert, Eigenkapital im Objekt. Am Ende: Gewinn bei Verkauf und Eigenkapitalrendite (IRR).
- **Sensitivität (Tornado-Diagramm):** Wie stark ändern sich Cashflow und Kaufpreisempfehlung, wenn jeder Parameter einzeln um ±10 % (Zins: ±0,5 Pp) schwankt? So sieht man, welche Annahme am meisten zählt.
- **Szenarien:** Die aktuelle Einstellung lässt sich unter einem Namen speichern („Bank-Angebot A“, „nach Sanierung“, „Verhandlungsziel“). Bis zu drei Szenarien werden nebeneinander verglichen. Gespeicherte Szenarien erscheinen in der Detailansicht und können über MCP gelesen werden. Sie ändern weder Score noch Profil.

**5. Was-wäre-wenn: Ranking-Simulation**
- Profil wählen, dann per Regler und Feldern KPI-Gewichte, Normalisierungsgrenzen, Ausschluss-Schwellen und alle Finanzannahmen des Profils (inkl. Ziel-Cashflow) ändern
- Das Ranking samt Kaufpreisempfehlungen wird **sofort neu berechnet** (im Speicher, mit derselben `scoring`-Logik) und nichts wird gespeichert
- Anzeige der Auf- und Absteiger im Vergleich zum aktuellen Ranking (▲▼ Plätze)
- Button **„Als Profil übernehmen“** öffnet den Konfigurations-Editor mit den geänderten Werten und einer Vorschau der Änderungen

**Gemeinsame Rechenbasis:** Score, Kaufpreisempfehlung, Detailansicht, beide Simulationen und MCP nutzen dieselbe Funktion `finance.simulate(listing, annahmen) → ergebnis`. Ohne geänderte Annahmen liefert die Simulation exakt die Werte der Detailansicht. Ein Test stellt das sicher.

> Die Steuerrechnung ist bewusst vereinfacht (AfA, Zinsen und Bewirtschaftung als Werbungskosten, persönlicher Grenzsteuersatz). Sie ersetzt keine Steuerberatung und ist in der Oberfläche als Näherung gekennzeichnet.

**6. Konfiguration**
- `settings.yaml` und die Profile als Formulare (aus dem Pydantic-Schema erzeugt), zusätzlich ein YAML-Rohmodus für Fortgeschrittene
- Speichern läuft so ab:
  1. Prüfen
  2. Vorschau der Änderungen (Diff)
  3. Backup nach `config/.history/`
  4. Schreiben
  5. Eintrag in `config_change`
  6. **automatische Neuberechnung der Scores**
- Profile anlegen, kopieren, aktivieren und deaktivieren
- Backups ansehen und wiederherstellen

**7. Läufe**
- Buttons: **„Kompletten Lauf starten“** (optional je Profil), **„Digest jetzt senden“**
- Liste der Jobs mit Status, Dauer, Auslöser (Zeitplan/Oberfläche/MCP) und Log-Ansicht
- Kennzahlen je Lauf aus `run_log`

### 10.3 MCP-Server

**Lese-Werkzeuge**

| Tool | Zweck |
|---|---|
| `list_profiles` | Aktive Profile mit Kurzbeschreibung der Kriterien |
| `search_listings` | Suche mit Filtern (Profil, Score, Rendite, Preis, Preisabstand, Ort, Status, Portal, Zeitraum, Volltext), sortierbar, begrenzt |
| `get_listing` | Alle Daten eines Angebots inkl. Extraktion, Score-Aufschlüsselung, Kaufpreisempfehlung mit Rechenweg, Status, Notizen, Preisverlauf |
| `get_top_listings` | Top-N je Profil |
| `explain_score` | Warum hat das Angebot diesen Score? KPIs, Gewichte, Ausschlusskriterien, Schätzungen |
| `compare_listings` | 2–5 Angebote nebeneinander |
| `get_changes` | Neu, Preisänderungen, entfernt seit Zeitpunkt X |
| `get_stats` | Bestand, Verteilungen, Zustand je Portal |
| `simulate_scoring` | Ranking-Simulation mit geänderten Gewichten bzw. Annahmen, **ohne Speichern** |
| `simulate_listing` | Objekt-Simulation: ein Angebot mit geänderten Parametern durchrechnen (alle Parameter aus 10.2 Nr. 4), inkl. Kaufpreisempfehlung, Break-even-Werten und Sensitivität, **ohne Speichern** |
| `get_scenarios` | Gespeicherte Szenarien eines Angebots mit Annahmen und Ergebnissen |
| `get_jobs` | Status laufender und letzter Läufe |

**Schreib-Werkzeuge** (einzeln in `settings.yaml` freischaltbar)

| Tool | Zweck |
|---|---|
| `set_status` | Status setzen, optional mit Notiz (z. B. „Markiere 42 als angefragt“) |
| `add_note` | Notiz zu einem Angebot hinzufügen |
| `start_run` | Kompletten Lauf anstoßen (optional je Profil) |
| `reextract_listing` | Ein Angebot neu von Claude auswerten lassen |
| `send_digest_now` | Digest außer der Reihe erzeugen und senden |

**Bewusst nicht** über MCP möglich sind Änderungen an der Konfiguration, das Überschreiben extrahierter Werte, das Speichern von Szenarien und das Löschen von Daten. Das geht nur über die Oberfläche.

- **Zusatz-Ressource:** Beschreibung der Felder, KPIs und Status-Werte, damit Claude Fragen ohne Raten richtig beantwortet.
- **Ausgabeformat:** kompaktes JSON mit Links zur Detailansicht, Listen sind begrenzt (Standard 20). So bleibt der Kontext von Claude klein.
- Jede Schreibaktion wird mit der Quelle `mcp` protokolliert (`workflow_history`, `note`, `job`).

**Einbindung in Claude** (Details in Phase 7 prüfen):

Claude Code:

```bash
claude mcp add --transport http immo http://immo-minipc:8710/mcp --header "Authorization: Bearer <TOKEN>"
```

Claude Desktop: Remote-Connectors laufen über die Cloud und erreichen das Heimnetz nicht. Deshalb wird der Server als lokaler stdio-Eintrag über eine Brücke (z. B. `mcp-remote`) eingebunden, die die LAN- bzw. Tailscale-Adresse anspricht.

### 10.4 Sicherheit

- **Netz:** Der Server lauscht nur auf localhost, der LAN-Adresse und der Tailscale-Adresse. Es gibt keine Portfreigabe im Router. Unterwegs läuft der Zugriff über das Tailscale-VPN auf Handy oder Laptop.
- **HTTPS:** optional über `tailscale serve` bzw. Tailscale-Zertifikate.
- **Oberfläche:** ein Benutzer mit Passwort-Login (Argon2-Hash in `.env`), Sitzungs-Cookie (HttpOnly, SameSite) und CSRF-Schutz für Formulare und HTMX-Aktionen.
- **MCP:** eigenes Bearer-Token (in `.env`), unabhängig vom Login der Oberfläche. Schreib-Werkzeuge sind einzeln abschaltbar.
- **Job-Runner:** Er startet nur festgelegte Befehle (keine freien Parameter, Profil-IDs werden geprüft), mit Zeitlimit und Sperre.
- **Konfigurations-Editor:** Er schreibt nur in `config/`, prüft vor dem Speichern und legt immer ein Backup an.

---

## 11. Betrieb auf dem Mini-PC (Windows 11)

### 11.1 Laufzeitumgebung (festgelegt)

**Fredy läuft in Docker, alles andere lokal unter Windows.**

| Was | Wo | Start |
|---|---|---|
| Fredy | Docker Desktop (Container), Port 9998 nur lokal bzw. im LAN | Docker-Autostart + `restart: unless-stopped` |
| Fredys DB | Container-Volume, wird nur über Fredys API gelesen | – |
| Python 3.12 + `.venv` | Windows, z. B. `C:\E\ai-workspace\immo-search` | – |
| `data\immo.db` | Windows-Dateisystem (NTFS), WAL-Modus | – |
| `immo-server` (Uvicorn, Port 8710) | Windows-Prozess im Benutzerkonto | Aufgabenplanung „bei Anmeldung“, Neustart bei Absturz |
| Läufe (`run.ps1` → `claude -p "/immo-analyse …"`) | Windows-Prozess im selben Benutzerkonto | Aufgabenplanung (Zeitplan) bzw. Job-Runner des Servers |
| Claude Code | Windows, mit deiner Anmeldung | – |
| Tailscale | Windows-Client | Windows-Dienst |

```
Windows 11
├─ Docker Desktop ── [Fredy] :9998 ◄──────────── HTTP ──┐
│                                                        │
└─ Benutzerkonto                                         │
   ├─ immo-server (:8710)  ──┐                           │
   ├─ run.ps1 → claude -p ───┼─► C:\E\ai-workspace\immo-search\data\immo.db
   └─ scripts\*.py ──────────┘──────────────────────────┘
```

**Begründung:**
- **Alle Zugriffe auf `immo.db` erfolgen von derselben Seite** (Windows). Datei-Sperren und WAL von SQLite funktionieren dann zuverlässig. Ein Mischbetrieb über die Grenze zwischen Docker und Windows wird bewusst vermieden.
- **Claude Code** nutzt die normale Anmeldung des Benutzerkontos. Zeitplan und Job-Runner starten `claude -p` im selben Konto, im Normalfall ohne zusätzliches Token. `run.ps1` übernimmt ein Token aus `.env` nur, wenn eines gesetzt ist (Rückfallebene, siehe 9.2).
- **Einfache Fehlersuche:** Logs, DB und Konfiguration liegen direkt im Dateisystem.

**Absicherung des unbeaufsichtigten Claude-Tasks** (läuft ohne Container-Abschottung):
- `.claude/settings.json` mit einer engen Positivliste: Lesen im Projekt, `python scripts/*.py`, Schreiben nur in `data/`. Alles andere ist verboten (`deny`), kein Netzzugriff außer über die Skripte.
- `run.ps1` startet Claude immer im Projektordner, mit Zeitlimit und Protokoll jedes Laufs.
- Optional, sicherer: ein eigenes Windows-Standardkonto „immo“ ohne Admin-Rechte für Server, Läufe und eine eigene Claude-Anmeldung (dann per `claude setup-token`). Dieses Konto hat nur Zugriff auf `C:\E\ai-workspace\immo-search`.

### 11.2 Weitere Betriebsthemen

| Thema | Umsetzung |
|---|---|
| Docker | Docker Desktop (WSL2), Autostart beim Systemstart. Läuft nur mit angemeldetem Benutzer, deshalb automatische Anmeldung mit gesperrtem Bildschirm einrichten. Energiesparen und Ruhezustand deaktivieren. |
| Fredy | `docker compose` mit festem Image-Tag (kein `latest`) und `/db` als Bind-Mount, z. B. `C:\E\docker\fredy\db` |
| Fredy absichern | Nur im LAN erreichbar, Admin-Passwort ändern, Analytics-Ping prüfen und deaktivieren |
| Abhängigkeiten | in `pyproject.toml`, feste Versionen (Lock-Datei) |
| Tailscale | Auf dem Mini-PC, Handy und Laptop. MagicDNS-Name, z. B. `immo-minipc` |
| Geheimnisse | `.env` (Telegram-Token, SMTP-Zugang, Fredy-Zugang, UI-Passwort-Hash, MCP-Token), steht in `.gitignore` |
| Backup | Täglich `immo.db` (per SQLite-Backup-API, konsistent auch während des Betriebs), `config/` und Fredy-`/db` sichern, z. B. auf NAS oder Cloud, mit Aufbewahrungsfrist |
| Überwachung | `run_log` + Telegram-Alarm bei Fehlern. „Health“-Prüfung: Jedes Portal muss innerhalb von X Tagen mindestens 1 Angebot liefern. Ein `/health`-Endpunkt des Servers wird vom Wrapper geprüft. |
| Updates | Fredy-Updates bewusst einspielen (Release Notes lesen, vorher Backup) |
| Deployment | Das Projekt liegt in Git und wird auf dem Mini-PC geklont. Änderungen werden auf dem Entwicklungsrechner gemacht und dann per `git pull` übernommen, danach wird der Server neu gestartet. Konfigurationsänderungen aus der Oberfläche werden auf dem Mini-PC committet. |

---

## 12. Projektstruktur

```
immo-search/
  PLAN.md
  CLAUDE.md                       ← Einstieg für neue Claude-Sitzungen: Stand, nächster Schritt, Konventionen
  README.md
  docs/SETUP-MINIPC.md            ← Einrichtung Phase 1
  pyproject.toml
  docker/
    fredy/docker-compose.yml
  config/
    settings.yaml
    profiles/mfh-beispiel.yaml
    .history/                     (Backups, nicht im Git)
  src/immo/                       ← gemeinsame Logik
    config.py  db.py  models.py  filters.py  kpis.py  scoring.py
    finance.py  fredy_client.py  extraction.py  notify.py  jobs.py
    sync.py  parse_attrs.py  claude_io.py (pending/save)  cli.py
    server/
      app.py                      (FastAPI, Login, Routing)
      web/                        (Routen + Jinja2-Templates + HTMX-Partials, static/)
      api/                        (REST-Endpunkte für HTMX/Was-wäre-wenn)
      mcp/                        (FastMCP-Tools & Ressourcen)
  scripts/                        ← dünne CLI-Einstiege
    sync.py  parse_attrs.py  pending.py  save.py  score.py  notify.py  serve.py
    dev_seed.py                   (nur Entwicklung: Testanzeigen in eine Dev-DB laden)
  .claude/
    settings.json
    skills/immo-analyse/ (SKILL.md, extraction_schema/, templates/)
  data/        (immo.db, Logs – nicht im Git)
  tests/       (Fixtures mit Beispielanzeigen, Tests für Filter/KPIs/Score, API- und MCP-Tests)
  run.ps1
  .env.example
```

---

## 13. Umsetzungsphasen

| Phase | Inhalt | Fertig, wenn … |
|---|---|---|
| **1 – Fredy aufsetzen** | Docker Desktop + Fredy auf dem Mini-PC, Jobs für IS24, Immowelt und Kleinanzeigen (MFH, Beispielregion), 2–3 Tage laufen lassen | Angebote aller 3 Portale kommen an. Die offenen Punkte 1–8 aus Abschnitt 14 sind geklärt. |
| **2 – Kern & Sync** | Projektstruktur, Paket `immo/`, Konfiguration samt Pydantic-Prüfung, `fredy_client`, `sync` mit `fetch_filter`, eigene DB (WAL), Preisverlauf | `sync` lässt sich beliebig oft ausführen, ohne doppelte Einträge. Der Filter wirkt nachweisbar. |
| **3 – Extraktion** | `parse_attrs`, Schema MFH, `pending`/`save`, erste SKILL.md, manueller Testlauf in Claude | Für ≥ 80 % der Testangebote mit Mietangabe wird die Ist-Miete korrekt erkannt. |
| **4 – Scoring & Finanzen** | KPI-Register, Normalisierung, Ausschlusskriterien, Score-Formel, Finanzrechner `finance.simulate()`, **Kaufpreisempfehlung** inkl. Sonderfälle und Zinsspanne, Tests | Ranking und Kaufpreisempfehlung stimmen mit einer Handrechnung für 5 Beispielangebote überein. Beim empfohlenen Preis ergibt die Rechnung exakt den Ziel-Cashflow. |
| **5 – Benachrichtigung & Digest** | `notify` (Telegram, SMTP), Digest-Vorlage, Modi `run` und `digest` | Ein kompletter Lauf liefert Telegram-Meldungen und eine Digest-Mail. |
| **6 – Automatisierung** | `run.ps1`, Windows-Aufgabenplanung, Sperre, Berechtigungen, Anmeldung (Token nur falls nötig), Backup, Überwachung | Läuft eine Woche unbeaufsichtigt ohne Eingriff. |
| **7 – Server: Lesen** | `immo-server` mit Login, Übersicht, Liste, Detailansicht. MCP mit allen Lese-Werkzeugen, Tailscale-Zugang, Links in Telegram/Digest | Oberfläche ist zu Hause und unterwegs per VPN nutzbar. Claude Code/Desktop beantwortet Fragen wie „Top 5 MFH über 6 %?“ über MCP. |
| **8 – Server: Aktionen** | Status-Workflow & Notizen, Job-Runner (Lauf, Neu auswerten, Digest), Ranking-Simulation, Konfigurations-Editor mit Prüfung, Diff, Backup und Neuberechnung. MCP-Schreib-Werkzeuge | Alle Aktionen funktionieren in Oberfläche und MCP, jede Änderung ist protokolliert. Eine Konfigurationsänderung in der Oberfläche führt zu korrekt neu berechneten Scores und Kaufpreisempfehlungen. |
| **8b – Objekt-Simulation** | Erweiterung von `finance.simulate()` um Mehrjahresverlauf, Zinsbindung/Anschluss, zweites Darlehen, Steuern, IRR, Break-even, Sensitivität. Oberfläche (Regler, Verlauf, Tornado-Diagramm, Szenario-Vergleich), Tabelle `scenario`, MCP `simulate_listing` und `get_scenarios` | Ohne Änderungen stimmt die Simulation mit der Detailansicht überein. Verlauf und IRR stimmen für 2 Beispiele mit einer Tabellenkalkulation überein. Szenarien lassen sich speichern, vergleichen und löschen. |
| **9 – Ausbau** (optional) | Karte (Leaflet/OSM), Lernen aus deinem Status-Verlauf (Gewichte vorschlagen), weitere KPIs (Mietpotenzial mit Mietspiegel), weitere Portale/Profile | nach Bedarf |

> Die Phasen 7–8 bauen auf der DB aus den Phasen 2–4 auf. Mit einfachen Ansichten kann Phase 7 auch parallel zu 5–6 entstehen.

### 13.1 Stand der Umsetzung (18.10.2026)

| Phase | Stand | Nachweis / Anmerkung |
|---|---|---|
| 1 | **vorbereitet, pausiert** | Anleitung `docs/SETUP-MINIPC.md`, `docker/fredy/setup.ps1` (Fredy 29.3.0), Diagnose `scripts/check_fredy.py`. Pausiert, weil der Mini-PC eine QEMU-VM ohne verschachtelte Virtualisierung war und Docker Desktop nicht lief. Er wird neu mit Windows 11 direkt auf der Hardware installiert. |
| 2 | fertig | Tests: Sync idempotent, URL-Normalisierung, `fetch_filter` je Profil, Preisverlauf, entfernt/reaktiviert, fehlerhafter Job markiert nichts als entfernt. Gegen ein echtes Fredy noch **nicht** geprüft. |
| 3 | fertig | Ist-Miete 10/10 korrekt, alle 45 erwarteten Werte stimmen. Geprüft nur an 12 **selbst geschriebenen** Testanzeigen (`tests/fixtures/mfh_anzeigen.json`), mit echten Anzeigen erneut messen. |
| 4 | fertig | 5 Beispiele gegen Handrechnung (`tests/test_finance.py`). Ziel-Cashflow beim empfohlenen Preis exakt, 500 Zufallsfälle. |
| 5–9 | offen | Nächste Phase nach Abschluss von Phase 1: 5 (Benachrichtigung & Digest). |

Commits: `f62f8b2` (Phasen 2+3), `8a5989d` (Phase 4), `4bc6e12` (Vorbereitung Phase 1), danach die Doku zur Übergabe.

---

## 14. Offene Punkte

**In Phase 1 prüfen:**
1. **Fredy-API:**
   - Welche Endpunkte gibt es, wie läuft die Anmeldung?
   - Lassen sich Angebote je Job und seit einem Zeitstempel abrufen?
   - Falls nein: SQLite nur lesend (Schema dokumentieren, Gefahr bei Fredy-Updates).
2. **Erstbefüllung:** Speichert Fredy beim ersten Lauf **alle** aktuellen Treffer oder nur neue? Gegebenenfalls einen Job neu anlegen bzw. zurücksetzen.
3. **Details je Portal:**
   - IS24 lädt das Exposé nach. Was liefern Immowelt und Kleinanzeigen?
   - Ist die Beschreibung vollständig oder gekürzt? Davon hängt die Qualität der Extraktion ab.
4. **Such-URLs für MFH:** Funktioniert die Such-URL für Mehrfamilienhäuser in Fredys IS24-Übersetzer? Es gab in der Vergangenheit Fehler „Real estate type not found“ bei manchen Objektarten.
5. **Duplikate über Portale:** Liefert Fredy eine Duplikat-Kennung? In der Tabelle `listings` ist keine zu sehen. Bis das geklärt ist, bildet jedes Angebot seine eigene `duplicate_group`. Sonst eine eigene Erkennung (Adresse/Koordinaten + Fläche + Preis) in `sync`.
6. **Objektart in den Daten:** Kann `sync` die Objektart und den Job je Angebot sicher zuordnen? Davon hängt die Zuordnung zum Profil ab.
7. **Ortsdaten:** Sind PLZ und Koordinaten in Fredy-Daten verlässlich vorhanden? Sonst werden sie per Geocoding (OSM/Nominatim, sparsam und zwischengespeichert) ergänzt.
8. **Claude ohne Oberfläche:** Hält die normale Anmeldung im unbeaufsichtigten Betrieb (Aufgabenplanung bei gesperrtem Bildschirm)? Falls nein: `claude setup-token` als Rückfallebene. Außerdem: Verhalten bei erreichtem Nutzungskontingent (der Lauf soll sauber abbrechen und beim nächsten Mal weitermachen).

**In Phase 7 prüfen:**

9. **MCP-Anbindung von Claude Desktop** an einen MCP-Server im LAN (stdio-Brücke wie `mcp-remote` und Anmeldung per Token). Claude Code direkt über HTTP.
10. **Job-Runner startet `claude -p`** aus dem Serverprozess: Anmeldung, Arbeitsverzeichnis, Zeitlimit, Abbruch.

---

## 15. Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| IS24-App-Schnittstelle (inoffiziell) fällt weg | Überwachung je Portal, kurzfristig E-Mail-Suchagent als Reserve, auf Fredy-Updates warten |
| Fredy wird nur von einer Person gepflegt | Festes Image-Tag, Zugriff auf Fredy in `fredy_client` kapseln, damit sich die Quelle austauschen lässt |
| Fredy-Update ändert API oder Schema | Fester Tag, Vertragstests in `tests/`, Update erst nach Test |
| Claude extrahiert falsch | Belegstelle Pflicht, Schema-Prüfung, Quelle und Konfidenz in Detailansicht und Digest sichtbar, „Neu auswerten“ per Klick |
| Mietangaben fehlen oft | Als „unvollständig“ markieren statt verwerfen. Optional Schätzung, deutlich gekennzeichnet. |
| SQLite-Sperrkonflikte (Server liest, Lauf schreibt) | WAL-Modus, `busy_timeout`, kurze Transaktionen, nur ein schreibender Lauf gleichzeitig, Server läuft auf demselben Dateisystem (nicht in Docker) |
| Fehlerhafte Konfiguration über die Oberfläche | Pydantic-Prüfung, Diff-Vorschau, Backup vor jedem Speichern, Wiederherstellung in der Oberfläche |
| Unbefugter Zugriff auf Oberfläche/MCP | Kein Internetzugang (nur LAN + Tailscale), Login + CSRF, eigenes MCP-Token, Schreib-Werkzeuge einzeln abschaltbar |
| Claude stößt über MCP zu viele Läufe an | Sperre + Warteschlange, Mindestabstand zwischen manuellen Läufen (konfigurierbar), alles in `job` protokolliert |
| Mini-PC aus oder Update-Neustart | Autostart von Docker, Server und Tailscale, Ruhezustand aus, Neustart-Fenster für Windows Update festlegen, Alarm bei fehlendem Lauf |
| Kontingent erschöpft | Nur neue Angebote auswerten, kompakte Eingabe, Lauf bricht sauber ab und setzt beim nächsten Mal fort |

---

## 16. Rechtliches & Datenschutz (Hinweis, keine Rechtsberatung)

- Nur private, nicht-kommerzielle Nutzung, keine Weitergabe oder Veröffentlichung der Daten
- Moderate Abrufhäufigkeit, keine Umgehung von Schutzmechanismen
- Fredys Lizenz (Apache 2.0 + Commons Clause) erlaubt die private Nutzung, verbietet aber den Verkauf
- Telefonnummern und Namen von Anbietern nur lokal speichern. Die Oberfläche ist nicht öffentlich, und der Digest geht nur an dich.
