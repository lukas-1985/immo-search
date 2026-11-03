# Immo-Suche – Konzept & Umsetzungsplan

> Persönliche Meta-Suche für Kapitalanlage-Immobilien (Start: Mehrfamilienhäuser).
> Stand: 03.11.2026 · Status: Phasen 2–4, 7, 8, 8b und 8c (Steuern) umgesetzt (ohne Digest-Teile), Phase 6 umgesetzt (Abnahme: eine Woche unbeaufsichtigt steht aus), Phase 1 fast fertig (Fredy läuft auf dem Mini-PC), 5 offen, 9 optional.

---

## 0. Kurzfassung

- **Fredy** (Open-Source-Tool, Docker) übernimmt das Einsammeln der Angebote von ImmoScout24, Immowelt (inkl. Immonet), Kleinanzeigen und weiteren Portalen.
- Eine eigene **Analyse-Schicht** liegt darüber und besteht aus zwei Teilen:
  - **Python** erledigt alles Deterministische: Daten holen, filtern, speichern, Score und Finanzkennzahlen berechnen.
  - **Codex mit ChatGPT-Anmeldung** erledigt alles, was Urteilsvermögen braucht: Freitexte auswerten, Auffälligkeiten erkennen, den Digest mit Begründungen schreiben.
- Der **Codex-Skill `immo-analyse`** verweist auf die Python-Pipeline. Zeitplan und Job-Runner starten `run.ps1`; Python steuert die KI-Aufrufe ohne interaktive Skill-Ausführung.
- **Alles ist zentral konfigurierbar**, über ein oder mehrere *Suchprofile* (YAML):
  - Objektart, Region, Fläche, Preis usw.
  - Ausschlusskriterien
  - Score-Formel
  - Finanzannahmen
- **Kaufpreisempfehlung:** Für jedes Angebot wird automatisch der Kaufpreis berechnet, bei dem der monatliche Cashflow neutral ist (Ziel einstellbar). Er wird überall angezeigt: Liste, Detailansicht, Telegram, Digest, MCP.
- **Was-wäre-wenn-Simulation:** Kauf, Miete, Finanzierung und Kosten je Objekt veränderbar. Alle Kennzahlen werden neu berechnet. Außerdem lässt sich eine Kennzahl als Ziel festlegen (Cashflow, Bruttorendite, Nettoanfangsrendite), dann wird Kaufpreis, Miete, Zins oder Eigenkapital daraus zurückgerechnet. Szenarien lassen sich speichern. Dazu eine Simulation des gesamten Rankings.
- **Ausgabe:** Sofortmeldung über Telegram bei Top-Treffern und ein täglicher Digest per E-Mail.
- **Eigener kleiner Server `immo-server`** auf Basis der **eigenen SQLite-DB**. Er stellt zwei Dinge bereit:
  - eine **Web-Oberfläche**: Übersicht, Liste, Detailansicht, Status-Verfolgung, Läufe anstoßen, Konfigurations-Editor, Kaufpreisempfehlung, Objekt- und Ranking-Simulation
  - einen **MCP-Server**: Codex kann suchen, vergleichen und erklären, außerdem Status und Notizen setzen und Läufe anstoßen.
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
- Den Datenbestand im Gespräch mit Codex auswerten

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
| Analyse | Python steuert die Pipeline und ruft Codex für strukturierte Extraktionsantworten auf; der Skill verweist auf dieselben Skripte |
| Datenzugriff | Das Python-Skript holt die Daten **selbst** bei Fredy (HTTP-API, ersatzweise SQLite nur lesend). |
| Oberfläche & MCP | Eigener Server `immo-server` (Python/FastAPI) auf der **eigenen** DB. Fredys Oberfläche und MCP dienen nur noch der Fehlersuche bei Rohdaten. |
| Zugriff | Heimnetz + unterwegs per VPN (Tailscale), **ein** Benutzer mit Login |
| Konfiguration | Die YAML-Dateien bleiben maßgeblich. Die Oberfläche schreibt geprüft und mit Backup in sie zurück. |
| MCP-Schreibrechte | Status & Notizen setzen, Läufe anstoßen. Konfiguration und Extraktion kann Codex **nicht** ändern. |
| Zweck | Kapitalanlage |
| Objektart (Start) | Mehrfamilienhaus, zentral im Suchprofil konfigurierbar |
| Score | Konfigurierbare Formel aus Kennzahlen (KPIs), Standard: Bruttorendite |
| Kaufpreisempfehlung | Preis für neutralen Cashflow (Ziel-Cashflow einstellbar), für jedes Angebot deterministisch in `score` berechnet, geschlossene Formel |
| Simulation | Eine gemeinsame Rechenfunktion `finance.simulate()` für Score, Kaufpreisempfehlung, Oberfläche und MCP. Szenarien je Objekt speicherbar. |
| Region / Budget | Platzhalter im Beispielprofil, legst du selbst fest |
| Benachrichtigung | Telegram (Sofortmeldung) + E-Mail (täglicher Digest), jeweils mit Link zur Detailansicht |
| Betrieb | Mini-PC mit Windows 11, rund um die Uhr. **Nur Fredy läuft in Docker.** Alles Eigene läuft lokal unter Windows: Python-Skripte, `immo-server`, Codex CLI, `immo.db`. Siehe Abschnitt 11.1. |

---

## 3. Architektur

```text
Fredy (Docker, API oder SQLite read-only)
  -> sync -> parse_attrs -> extract.py -> score -> health
                              |
                   Python: pending -> codex exec -> save
                   (strukturierte Antwort, geprüfte Speicherung)

Windows-Aufgabenplanung -> scripts/lauf.py -> run.ps1 -> Pipeline
Weboberfläche / MCP -> Job-Runner ----------> run.ps1 -> Pipeline
Codex-Skill immo-analyse ------------------> run.ps1 / extract.py

Alle Python-Bausteine nutzen die eigene data/immo.db (SQLite, WAL).
immo-server (FastAPI, Oberfläche + MCP) liest und schreibt diese DB.
Codex erhält nur Vorlagen und Fachregeln; es beschreibt die DB nicht selbst.
```

**Kernprinzip:** Eine einzige Logik in `immo/`. CLI-Skripte, Web-Oberfläche und MCP-Server nutzen **dieselben** Funktionen für Filter, KPIs und Score. Oberfläche und MCP verwenden dieselben Berechnungen; der künftige Digest soll ebenfalls darauf aufbauen.

**Wer macht was?**

| Baustein | Aufgabe | Deterministisch? |
|---|---|---|
| Fredy | Portale abfragen und Exposé-Details nachladen; portalübergreifende Duplikate erkennt die eigene `duplicates.py` | – |
| `sync` | Neue und geänderte Angebote holen, Vorfilter anwenden, in eigener DB speichern, Preisverlauf führen | ja |
| `parse_attrs` | Strukturierte Merkmale per Regeln aus der Attributliste bzw. dem Text ziehen (z. B. „Mieteinnahmen pro Jahr“) | ja |
| Codex über Python | Lücken aus dem Freitext füllen und belegte Risiken erkennen; Digest erst in Phase 5 | nein, erfolgreiches Ergebnis wird gespeichert |
| `save` | Codex-Extraktion gegen das JSON-Schema prüfen und speichern | ja |
| `score` | Ausschlusskriterien, KPIs, Score, Finanzierung, Ranking | ja |
| `notify` (geplant) | Telegram und E-Mail versenden (Phase 5) | ja |
| `immo-server` | Oberfläche, REST-API, MCP, Job-Runner, Konfigurations-Editor | ja |

---

## 4. Ablauf eines Laufs

```text
run.ps1 [-Profil <profil>] [-Db <pfad>] [-ConfigDir <pfad>]

1. sync         Angebote holen, fetch_filter anwenden, Änderungen speichern
2. parse_attrs  Eindeutige Merkmale regelbasiert extrahieren
3. extract.py   Python wählt offene Angebote und steuert Codex-Aufrufe
   pending      Kompakte Vorlage: gesuchte/bekannte Felder, Titel und Text
   Codex        Strukturierte Antwort nach Transport- und Fachschema
   save         Prüfen und speichern (neue KI-Quelle openai)
4. score        Hard-Filter -> KPIs -> Score -> Ranking
5. health       Zustand prüfen und protokollieren

-Listing <id> -Reextract: direkt KI-Neuauswertung, danach Bewertung;
                         kein Sync, Regel-Lauf oder Health-Schritt.
Phase 5 geplant: Telegram und E-Mail-Digest (derzeit nicht ausgeführt).
```

**Auslöser:** Aktuell werden nur Lauf und Neuauswertung ausgeführt. Benachrichtigungen, Digest-Zeitplan, Digest-Button und `send_digest_now` sind geplant (Phase 5).

| Auslöser | Modus |
|---|---|
| Windows-Aufgabenplanung | Läufe nach `schedule.run` (Standard alle 3 Stunden, 07–22 Uhr); `schedule.digest` ist für Phase 5 reserviert |
| Oberfläche („Kompletten Lauf starten“, „Neu auswerten (KI)“) | über den Job-Runner; Digest-Button erst in Phase 5 |
| MCP (`start_run`, `reextract_listing`) | über denselben Job-Runner; `send_digest_now` erst in Phase 5 |

**Sperre gegen parallele Läufe:** Zeitplan, Oberfläche und MCP teilen sich eine Sperre (Lock-Datei + Tabelle `job`). Der Server-Runner arbeitet Jobs nacheinander ab. Die zusätzliche Sperrdatei verhindert parallele Pipeline-Läufe; ein direkter konkurrierender run.ps1-Aufruf endet mit Exit 3.

**Wichtig:** Erfolgreich ausgewertete Angebote werden bei unverändertem Text und Schema nicht erneut vorgelegt.
- Ändert sich die Gewichtung oder Formel, rechnet `score` alle Angebote neu (Sekunden, ohne Codex). Das passiert auch automatisch nach dem Speichern der Konfiguration in der Oberfläche.
- Erneut vorgelegt werden Angebote bei geändertem Beschreibungstext (Hash), neuer Fachschema-Version, einem wiederholbaren Fehler oder ausdrücklicher Neuauswertung (Oberfläche, MCP oder `--listing … --reextract`). Der Anbieterwechsel allein löst keine Neuauswertung aus.

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
- Ein Profil bündelt all das an **einer** Stelle, liegt versioniert in Git und lässt sich auch ohne Codex nutzen.
- Der **Skill-Parameter wählt nur das Profil aus:** `/immo-analyse mfh-beispiel`. Ohne Parameter laufen alle aktiven Profile.

**Prüfung:** Ein Pydantic-Modell beschreibt die zulässige Struktur. CLI, Server und Konfigurations-Editor prüfen dagegen. Eine fehlerhafte Konfiguration wird nie gespeichert oder verwendet.

### 5.2 Drei Filterstufen

| Stufe | Wo | Worauf | Zweck |
|---|---|---|---|
| 1. Portalsuche | Fredy-Job (Such-URL des Portals) | was das Portal filtern kann | Grobe Vorauswahl, wenig Last |
| 2. **`fetch_filter`** | `sync`, **vor** dem Speichern | Felder, die Fredy liefert: Ort/PLZ/Umkreis, Preis, Fläche, Zimmer, Baujahr, Portal | Genauer eingrenzen, als es die Portale können. Spart Codex-Aufwand. |
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
| `cashflow_nach_steuern` | Cashflow − Steuer, pro Monat (vereinfacht, siehe 5.7). Verfügbar, im Profil `mfh-kl` nicht gewichtet | + Finanzierung, Steuern |
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
steuern:                 # vereinfachter Cashflow nach Steuern (Jahr 1), siehe 5.7
  grenzsteuersatz: 0.42  # persönlicher Grenzsteuersatz (ohne Soli/Kirchensteuer)
  gebaeudeanteil: 0.80   # Anteil Gebäude an Kaufpreis + Nebenkosten (Rest Grund und Boden); in der Simulation änderbar
  afa_satz: 0.02         # lineare AfA, fest (kein „auto“ nach Baujahr); in der Simulation änderbar
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

### 5.7 Steuern (vereinfacht, Phase 8c)

Cashflow nach Steuern für **Jahr 1**, Entscheidungen vom 20.10.2026. Es ist eine Näherung, keine Steuerberatung, und in der Oberfläche so gekennzeichnet.

```
AfA           = Gebäudeanteil · (P + P·n + S) · AfA-Satz          (Nebenkosten und Sanierung werden mit abgeschrieben)
Einkünfte  E  = M − B − Zinsen − AfA                               (Tilgung ist nicht absetzbar)
Steuer        = Grenzsteuersatz · E                                (E < 0 → negative Steuer = Ersparnis, Verluste voll verrechnet)
CF n. St.     = CF − Steuer
```

- Werte aus `settings.yaml → steuern`: Grenzsteuersatz 42 %, Gebäudeanteil 80 %, AfA-Satz 2 %, alle zentral für alle Profile. In der Objekt-Simulation lassen sich Gebäudeanteil und AfA-Satz übersteuern, der Grenzsteuersatz nicht.
- Wirkung: Anzeige in Detailansicht, Objekt-Simulation und Szenario-Vergleich, dazu die KPI `cashflow_nach_steuern`. **Score, Ranking und Kaufpreisempfehlung bleiben vor Steuern**, solange die KPI nicht im Profil gewichtet wird. Die Zielwert-Rückrechnung bietet bewusst keinen „Cashflow nach Steuern“ an.
- Die Steuerparameter gehören zum `config_hash` (`SCORING_VERSION` 2). Nach einer Änderung meldet die Simulation „Bewertung veraltet“, bis neu bewertet wurde.
- Ohne Miete gibt es keine Steuerrechnung.

---

## 6. Datenmodell (eigene DB `data/immo.db`, SQLite)

Getrennt von Fredys DB. Fredy wird nie beschrieben. Die DB läuft im **WAL-Modus** mit `busy_timeout`, damit Oberfläche und MCP lesen können, während ein Lauf schreibt.

| Tabelle | Inhalt |
|---|---|
| `listing` | `id`, `fredy_id`, `provider`, `url`, `titel`, `adresse`, `plz`, `ort`, `lat/lon`, `preis`, `flaeche`, `zimmer`, `baujahr`, `energieklasse`, `beschreibung`, `beschreibung_hash`, `bilder`, `first_seen`, `last_seen`, `status_portal` (aktiv/entfernt), `duplicate_group` |
| `listing_profile` | Zuordnung Angebot ↔ Profil (ein Angebot kann zu mehreren Profilen passen) |
| `price_history` | `listing_id`, `datum`, `preis` |
| `extraction` | `listing_id`, `feld`, `wert`, `quelle` (portal/regel/openai/claude (historisch)/schätzung), `konfidenz`, `belegstelle` (Textausschnitt), `schema_version`, `extracted_at` |
| `extraction_run` | Herkunft neuer Speicherungen: `listing_id`, `quelle`, effektives `modell` (falls ermittelbar), `beschreibung_hash`, `zeitpunkt`; historische Extraktionen werden nicht nachträglich zu OpenAI umetikettiert. |
| `extraction_status` | Stand der Codex-Auswertung je Angebot: `beschreibung_hash`, `schema_version`, `status` (ok/fehler), `versuche`, `letzter_fehler`. Grundlage für „nur einmal auswerten“. |
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

**Schema:** `resources/extraction_schema/<objektart>.json`, für MFH `mehrfamilienhaus.json` (Fachschema v1; Datenbankschema v3). Für Mehrfamilienhäuser:

| Feld | Typ | Beispiel |
|---|---|---|
| `wohneinheiten`, `gewerbeeinheiten` | int | 6, 1 |
| `jahresnettokaltmiete_ist` | € | 48.000 |
| `jahresnettokaltmiete_soll` | € | 54.000 |
| `leerstand_einheiten` | int | 1 |
| `provision` | Anteil inkl. MwSt. | 0.0357 (3,57 %), 0 bei provisionsfrei |
| `grundstueck_m2` | Zahl > 0 | 820 |
| `erbpacht`, `denkmalschutz`, `aufgeteilt_weg` | bool | false |
| `bauprojekt` | bool (true = Fertighaus-/Ausbauhaus-Angebot, kein Bestand) | false |
| `heizungsart`, `heizung_baujahr` | text, int | Gas, 2012 |
| `sanierungen` | Liste {Bauteil, Jahr} | Dach 2018, Fenster 2010 |
| `zustand` | Aufzählung | gepflegt / renovierungsbedürftig / Sanierungsstau |
| `risiken` | Liste | „Mietrückstände erwähnt“, „Feuchtigkeit Keller“ |
| `verhandlungsbasis` | bool | true |

**Regeln für Codex (in `resources/extraktionsregeln.md`, vom Skill referenziert):**
- Nur extrahieren, was im Text steht. Zu jedem Wert gehört die Belegstelle, nichts wird geraten.
- Zahlen werden normalisiert: Monatsmieten werden auf das Jahr hochgerechnet, und der Rechenweg wird festgehalten.
- Unsicherheit wird als `konfidenz` (hoch/mittel/niedrig) angegeben.
- Die Ausgabe ist nur JSON im Schema-Format. `save` lehnt ungültige Einträge ab, und das Angebot wird beim nächsten Lauf erneut vorgelegt (höchstens 3 Versuche, danach erst wieder bei geändertem Text oder auf Anforderung).

**Prüfungen in `save`** (gelten auch für Regelwerte):
1. JSON-Schema der Objektart. Ein Verstoß lehnt das ganze Ergebnis ab.
2. Die Belegstelle muss wörtlich in Titel oder Beschreibung stehen (Leerraum und Anführungszeichen egal, Teile mit „…“ getrennt). Sonst wird nur dieses Feld verworfen.
3. Plausibilität, z. B. Jahresmiete zwischen 1 % und 25 % des Kaufpreises (fängt Monats-/Jahresverwechslungen ab), Leerstand ≤ Einheiten.
4. Hat sich die Beschreibung seit `pending` geändert, wird das Ergebnis abgelehnt.

**Regelbasierter Parser:** nur eindeutige Bezeichnungen („Mieteinnahmen pro Jahr: …“), widersprüchliche Treffer ergeben keinen Wert. Da Regelwerte Vorrang vor Codex haben, gilt: lieber nichts finden als falsch finden.

**Reihenfolge der Quellen:**
1. Strukturierte Portaldaten
2. Regelbasierter Parser
3. KI: `openai` und historische `claude`-Werte (gleicher Rang)
4. Schätzung aus der Konfiguration

Höhere Stufen werden nicht überschrieben.

---

## 8. Benachrichtigungen

| Kanal | Auslöser | Inhalt | Erzeugt von |
|---|---|---|---|
| Telegram | Modus `run`, neuer Treffer mit Score ≥ `alert_threshold` oder deutliche Preissenkung bei einem Top-Angebot | Kurzinfo: Titel, Ort, Preis, **Kaufpreisempfehlung mit Abstand**, Bruttorendite, Score, **Link zur Detailansicht** + Portal-Link | `notify` (Vorlage, ohne Codex) |
| E-Mail | Modus `digest`, täglich oder per „Digest jetzt senden“ | Top-N je Profil mit Pro/Contra und Kaufpreisempfehlung (Abstand, Verhandlungsbasis laut Anzeige), neue Angebote, Preissenkungen, entfernte Favoriten, unvollständige Kandidaten („Miete fehlt – nachfragen“), offene Vorgänge je Status | Text von Codex, Versand per `notify` (SMTP) |

- **Links** zeigen auf `public_base_url` (Tailscale-Name). Sie funktionieren deshalb zu Hause und unterwegs, wenn das VPN aktiv ist.
- **Fredys eigene Benachrichtigungen** deaktivieren, sonst kommen Meldungen doppelt.
- **Fehlermeldungen** (Fredy nicht erreichbar, Portal liefert seit X Tagen nichts, Lauf fehlgeschlagen) gehen ebenfalls per Telegram.

---

## 9. Skill & Codex-Aufruf

### 9.1 Skill und gemeinsame Ressourcen

```text
.agents/skills/immo-analyse/SKILL.md  # Einstieg für interaktive Aufträge
resources/extraktionsregeln.md      # gemeinsame Fachregeln
resources/extraction_schema/mehrfamilienhaus.json
src/immo/ki_io.py                   # pending/save, Quellen und Status
src/immo/codex_extraktion.py         # Stapel, CLI-Aufruf, Prüfung und Protokoll
scripts/extract.py                  # dünner CLI-Einstieg
```

Der Skill startet dieselbe Pipeline wie Zeitplan und Oberfläche. Die unbeaufsichtigte Extraktion
benötigt keine Skill-Erkennung durch Codex: Python übergibt die Vorlagen, Fachregeln und Fachschemata direkt.

### 9.2 Aufruf und Grenzen

```powershell
codex login
codex login status
powershell -NoProfile -ExecutionPolicy Bypass -File run.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File run.ps1 -Profil mfh-kl
powershell -NoProfile -ExecutionPolicy Bypass -File run.ps1 -Listing 42 -Reextract
uv run python scripts/extract.py --profile mfh-kl  # nur KI-Extraktion
```

- **Anmeldung:** gespeicherte ChatGPT-Anmeldung desselben Windows-Kontos; kein Claude-Token und kein automatischer API-Fallback. Kontingente hängen vom Konto ab.
- **Konfiguration:** `settings.yaml` → `ki`: `cli_pfad: null` (automatische Programmsuche; alternativ expliziter Pfad), `modell: null` (CLI-Standard ohne Benutzerkonfiguration), `zeitlimit_s: 1800` (1–3600), `stapelgroesse: 20` (1–20), `max_stapel: 3` (1–3). Ein Modellname pinnt die Auswahl. Das effektive Modell wird, soweit im CLI-Log verfügbar, protokolliert.
- **Isolation:** `codex exec --ignore-user-config --ephemeral --skip-git-repo-check --sandbox read-only` in einem temporären Arbeitsordner; Shell und Websuche deaktiviert. Keine App-Geheimnisse in der Kindprozess-Umgebung. Anzeigentexte sind ausschließlich Daten.
- **Datenfluss:** strukturierte CLI-Ausgabe per `--output-schema`; Python prüft IDs, Hashes und gesuchte Felder, normalisiert das Transportformat und prüft anschließend Fachschema, Belegstellen und Plausibilität. Nur Python speichert in der DB.
- **Wiederholungen:** höchstens ein Korrekturversuch pro vollständig abgelehntem Ergebnis innerhalb eines Stapels; ein danach fehlerhafter Stapel beendet den Extraktionsschritt. Die Auswahl für spätere Läufe berücksichtigt `MAX_VERSUCHE = 3`; technische Fehler bleiben offen; zuordenbare Transportfehler werden wie Fachfehler einmal korrigiert. Strukturell ungültige Antworten oder fremde/doppelte/fehlende IDs brechen den Stapel ab. Das Gesamtzeitlimit gilt über alle Stapel und Korrekturen.
- **Teilfehler:** Nutzungslimit, CLI-Fehler, offene Restangebote und verworfene Felder ergeben Exit 2 des Extraktionsskripts. `run.ps1` bewertet anschließend weiter. Ein erfolgreich gespeichertes Angebot mit einzelnen verworfenen Feldern wird nicht automatisch erneut vorgelegt.
- **Protokolle:** `run_log` mit Schritt `ki`, CLI-Logs unter `data/logs/codex-*.log`, normalisierte gültige Antworten unter `data/extraction/codex-*.json`, Rohantworten vor der Prüfung unter `codex-*.antwort.json`.
- **Digest und Telegram:** noch nicht implementiert (Phase 5), daher kein Digest-Aufruf und kein automatischer Fehleralarm.

Einrichtung, Testdatenbanken, Sicherung und Rückkehr zum alten Stand: [docs/SERVER.md](docs/SERVER.md), Abschnitte 6–8.

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
- Risiken und Pro/Contra aus der Codex-Auswertung
- **Status setzen** mit optionaler Notiz, Verlauf der Statuswechsel
- Button „Neu auswerten (KI)“, Button **„Simulieren“** (öffnet die Objekt-Simulation mit den Werten dieses Angebots), Liste der gespeicherten Szenarien mit Kurzwerten (Kaufpreis, Miete, Cashflow, Bruttorendite)

**4. Was-wäre-wenn: Objekt-Simulation** (Phase 8b)

Ein Angebot mit eigenen Annahmen durchrechnen, nur für **Jahr 1**, also dieselbe Rechnung wie in der Detailansicht. Eigene Seite `/angebot/<id>/simulation?profil=<id>`, aufgerufen über den Button „Simulieren“. Ausgangspunkt sind immer die aktuellen Werte des Angebots (gleiche Herleitung wie in `scoring.bewerte`, also Merkmale + `annahmen_fuer`) und die Finanzannahmen des Profils. Neu gerechnet wird per Button **„Neu rechnen“** (Formular-POST wie bei der Ranking-Simulation, ohne JS). Geänderte Felder sind markiert, zeigen den Ausgangswert und lassen sich einzeln zurücksetzen. Dazu gibt es „Alles zurücksetzen“.

*Parameter (Vorwärtsrechnung):*

| Gruppe | Parameter |
|---|---|
| Kauf | Kaufpreis (€), Makler (%), Sanierung sofort (€). Grunderwerbsteuer und Notar sind sichtbar, aber fest aus dem Profil. |
| Miete | Jahresnettokaltmiete wahlweise als €/Jahr oder €/m² und Monat (Umrechnung über die Wohnfläche), Wohnfläche (m²) |
| Finanzierung | Eigenkapital (€ oder „= Kaufnebenkosten“), Zins, Tilgung, Tilgung einrechnen ja/nein |
| Kosten und Ziel | Bewirtschaftungsquote, Instandhaltung (€/m²/Jahr), Ziel-Cashflow pro Monat (für die Kaufpreisempfehlung) |
| Steuern (vereinfacht, 8c) | Gebäudeanteil, AfA-Satz (Grenzsteuersatz sichtbar, aber fest aus `settings.yaml`); Ergebnis zusätzlich: AfA, steuerliches Ergebnis, Steuer, Cashflow nach Steuern (5.7) |

*Zielwert-Rückrechnung:* Eine Kennzahl auf einen Wunschwert setzen, eine Größe auswählen, die daraus berechnet wird, dann „Berechnen“. Der berechnete Wert wird als geänderter Parameter übernommen, alle anderen Kennzahlen rechnen damit neu. Es wird immer nur eine Größe gelöst, alle anderen Eingaben bleiben fest. Alle Formeln sind geschlossen (linear, ohne Iteration). Bezeichnungen wie in 5.6: M Jahresmiete, q Bewirtschaftungsquote, i Instandhaltung €/m², A Wohnfläche, B = q·M + i·A, n Nebenkostenquote, S Sanierung, EK Eigenkapital, k = Zins + Tilgung (bzw. nur Zins), D = max(0, P·(1+n) + S − EK), C Ziel-Cashflow pro Monat.

| Zielwert | → Kaufpreis P | → Miete M | → Zins | → Eigenkapital |
|---|---|---|---|---|
| Cashflow/Monat = C | P* wie in 5.6 | M = (12·C + i·A + k·D) / (1 − q) | k = (M − B − 12·C) / D, Zins = k − Tilgung (falls eingerechnet) | D = (M − B − 12·C) / k, EK = P·(1+n) + S − D |
| Bruttorendite = r | P = M / r | M = r · P | – | – |
| Nettoanfangsrendite = r | P = (M·(1−q) − i·A) / (r·(1+n)) | M = (r·P·(1+n) + i·A) / (1 − q) | – | – |

- Zins und Eigenkapital lassen sich nur aus dem Cashflow-Ziel zurückrechnen, weil die Renditen nicht von der Finanzierung abhängen. Andere Kombinationen sind in der Oberfläche nicht wählbar.
- Ergebnisstatus wie bei der Kaufpreisempfehlung: `ok`, `nicht_erreichbar` (z. B. Zins müsste negativ sein, oder der Cashflow reicht selbst ohne Darlehen nicht), `immer_erreicht` (z. B. EK = 0 genügt schon, oder es fällt kein Kapitaldienst an), `miete_fehlt`. Ein nicht erreichbarer Zielwert ändert keinen Parameter und wird als Meldung angezeigt.
- Wird das Eigenkapital gelöst, wird daraus ein fester Betrag, auch wenn das Profil „= Kaufnebenkosten“ vorsieht. Bei P und M als Lösung mit EK „= Kaufnebenkosten“ gilt die angepasste Formel (EK wächst mit P mit, wie in 5.6).
- Die Zins-Lösung bei C = Ziel-Cashflow ist der „Break-even-Zins“, die Miet-Lösung die „Break-even-Miete“. Eigene Break-even-Kacheln gibt es deshalb nicht.

*Ergebnisse:* Tabelle mit **Ausgangswert | Simulation | Abweichung** für Nebenkosten, Gesamtinvestition, Darlehen, Rate/Monat, Cashflow/Monat, Bruttorendite, Faktor, Nettoanfangsrendite, Kaufpreisempfehlung (mit Zinsspanne ±0,5 Pp) und Preisabstand. Dazu der **Score** mit den simulierten Werten (gleiche Bewertungslogik inkl. Ausschlusskriterien, z. B. „würde bei Bruttorendite < 4 % ausgeschlossen“). Hinweise wie „Miete geschätzt“ bleiben sichtbar, solange die Miete nicht selbst gesetzt ist.

*Szenarien:*
- Die aktuelle Einstellung lässt sich unter einem Namen speichern („Bank-Angebot A“, „Verhandlungsziel“). Tabelle `scenario`: `annahmen_json` enthält nur die geänderten Parameter, `ergebnis_json` den Stand beim Speichern.
- Beim Laden wird mit den **aktuellen** Ausgangswerten neu gerechnet, die Änderungen werden darübergelegt. Weichen die Ergebnisse vom gespeicherten Stand ab (neue Extraktion, geänderte Profil-Annahmen), steht ein Hinweis dabei.
- Szenarien lassen sich laden, überschreiben, umbenennen und löschen. Bis zu drei werden nebeneinander verglichen (mit dem Ausgangswert als erster Spalte).
- Szenarien hängen am Angebot und am Profil. Sie ändern weder Score noch Ranking noch das Profil.
- **Kein MCP-Zugriff** (Entscheidung 19.10.2026). Rechnen und Szenarien gibt es nur in der Oberfläche.

*Nicht in 8b* (verschoben nach Phase 9, optional): Mehrjahresverlauf, Zinsbindung und Anschlusszins, zweites Darlehen, Steuern über Jahr 1 hinaus, IRR, Sensitivität/Tornado, Leerstand und Zielmiete mit Zeitpunkt, Regler mit Sofort-Neuberechnung, MCP `simulate_listing`/`get_scenarios`.

**5. Was-wäre-wenn: Ranking-Simulation**
- Profil wählen, dann per Regler und Feldern KPI-Gewichte, Normalisierungsgrenzen, Ausschluss-Schwellen und alle Finanzannahmen des Profils (inkl. Ziel-Cashflow) ändern
- Das Ranking samt Kaufpreisempfehlungen wird **sofort neu berechnet** (im Speicher, mit derselben `scoring`-Logik) und nichts wird gespeichert
- Anzeige der Auf- und Absteiger im Vergleich zum aktuellen Ranking (▲▼ Plätze)
- Button **„Als Profil übernehmen“** öffnet den Konfigurations-Editor mit den geänderten Werten und einer Vorschau der Änderungen

**Gemeinsame Rechenbasis:** Score, Kaufpreisempfehlung, Detailansicht, beide Simulationen und MCP nutzen dieselbe Funktion `finance.simulate(basis, **aenderungen) → ergebnis`. Die Zielwert-Rückrechnung (`finance.loese(...)`) liefert nur einen Parameterwert, gerechnet wird danach wieder mit `simulate()`. Ohne geänderte Annahmen liefert die Simulation exakt die Werte der Detailansicht. Ein Test stellt das sicher.

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
- Buttons: **„Kompletten Lauf starten“** (optional je Profil), **„Digest jetzt senden“** (erst Phase 5)
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
| `get_jobs` | Status laufender und letzter Läufe |

**Schreib-Werkzeuge** (einzeln in `settings.yaml` freischaltbar)

| Tool | Zweck |
|---|---|
| `set_status` | Status setzen, optional mit Notiz (z. B. „Markiere 42 als angefragt“) |
| `add_note` | Notiz zu einem Angebot hinzufügen |
| `start_run` | Kompletten Lauf anstoßen (optional je Profil) |
| `reextract_listing` | Ein Angebot neu von Codex auswerten lassen |
| `send_digest_now` (geplant, Phase 5) | Digest außer der Reihe erzeugen und senden |

**Bewusst nicht** über MCP möglich sind Änderungen an der Konfiguration, das Überschreiben extrahierter Werte, das Speichern von Szenarien und das Löschen von Daten. Das geht nur über die Oberfläche.

- **Zusatz-Ressource:** Beschreibung der Felder, KPIs und Status-Werte, damit Codex Fragen ohne Raten richtig beantwortet.
- **Ausgabeformat:** kompaktes JSON mit Links zur Detailansicht, Listen sind begrenzt (Standard 20). So bleibt der Kontext von Codex klein.
- Jede Schreibaktion wird mit der Quelle `mcp` protokolliert (`workflow_history`, `note`, `job`).

**Einbindung in Codex** (auf dem Mini-PC oder im Tailnet):

```powershell
codex mcp add immo --url http://immo-minipc:8710/mcp --bearer-token-env-var MCP_TOKEN
```

`MCP_TOKEN` muss beim Start des Clients als Umgebungsvariable gesetzt sein; `.env` wird vom MCP-Client
nicht automatisch geladen. Die Extraktionspipeline benötigt diese MCP-Verbindung nicht.
ChatGPT Web erreicht eine lokale/Tailscale-Adresse nicht allein aufgrund dieser Konfiguration.
Aktuelle Anleitung: [docs/SERVER.md](docs/SERVER.md), Abschnitt 4.

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
| Läufe (`run.ps1` → `scripts/extract.py` → `codex exec`) | Windows-Prozess im selben Benutzerkonto | Aufgabenplanung (Zeitplan) bzw. Job-Runner des Servers |
| Codex CLI | Windows, mit deiner Anmeldung | – |
| Tailscale | Windows-Client | Windows-Dienst |

```
Windows 11
├─ Docker Desktop ── [Fredy] :9998 ◄──────────── HTTP ──┐
│                                                        │
└─ Benutzerkonto                                         │
   ├─ immo-server (:8710)  ──┐                           │
   ├─ run.ps1 → extract.py ───┼─► C:\E\ai-workspace\immo-search\data\immo.db
   └─ scripts\*.py ──────────┘──────────────────────────┘
```

**Begründung:**
- **Alle Zugriffe auf `immo.db` erfolgen von derselben Seite** (Windows). Datei-Sperren und WAL von SQLite funktionieren dann zuverlässig. Ein Mischbetrieb über die Grenze zwischen Docker und Windows wird bewusst vermieden.
- **Codex CLI** nutzt die gespeicherte ChatGPT-Anmeldung desselben Windows-Kontos. Python startet `codex exec` aus Zeitplan und Job-Runner; Claude-Token werden nicht mehr gelesen.
- **Einfache Fehlersuche:** Logs, DB und Konfiguration liegen direkt im Dateisystem.

**Absicherung der unbeaufsichtigten KI-Extraktion:**
- Python kontrolliert Vorlagen, Stapelgrenzen, Zeitlimit und Speicherung. Codex läuft isoliert und liefert strukturierte Daten (Abschnitt 9.2).
- `run.ps1` hält die Sperrdatei und setzt die Bewertung nach einem KI-Teilfehler fort. Benachrichtigungen über solche Fehler fehlen bis Phase 5.
- Anmeldung und lokale Rechte müssen für das Windows-Konto der Aufgabenplanung verfügbar sein. Der echte Test unter gesperrtem Bildschirm und die einwöchige Abnahme stehen noch aus.

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

```text
immo-search/
  PLAN.md                         # Konzept, Status und offene Punkte
  AGENTS.md                       # Einstieg und Arbeitskonventionen
  CLAUDE.md                       # Verweis auf AGENTS.md für ältere Clients
  README.md
  docs/SETUP-MINIPC.md
  docs/SERVER.md
  pyproject.toml
  docker/fredy/docker-compose.yml
  config/
    settings.yaml
    profiles/
    .history/                     # Konfigurationsbackups, nicht im Git
  resources/
    extraktionsregeln.md
    extraction_schema/mehrfamilienhaus.json
  .agents/skills/immo-analyse/SKILL.md
  src/immo/
    config.py  db.py  models.py  filters.py  kpis.py  scoring.py
    finance.py  fredy_client.py  extraction.py  jobs.py
    sync.py  parse_attrs.py  ki_io.py  codex_extraktion.py  cli.py
    backup.py  health.py  duplicates.py  queries.py  workflow.py
    simulation.py  objekt_simulation.py  config_edit.py
    server/
      app.py  web.py  auth.py  mcp_tools.py
      templates/  static/
  scripts/
    sync.py  parse_attrs.py  pending.py  save.py  extract.py  score.py  serve.py
    lauf.py  backup.py  health.py  zeitplan.py  aufgabe.ps1  install_tasks.ps1
    dev_seed.py                    # Testanzeigen nur in eigener Dev-DB
  data/                           # immo.db, Logs, Extraktionen, Backups; nicht im Git
  tests/
  run.ps1
  .env.example
```

`notify.py` und Digest-Vorlagen sind erst für Phase 5 geplant.

---

## 13. Umsetzungsphasen

| Phase | Inhalt | Fertig, wenn … |
|---|---|---|
| **1 – Fredy aufsetzen** | Docker Desktop + Fredy auf dem Mini-PC, Jobs für IS24, Immowelt und Kleinanzeigen (MFH, Beispielregion), 2–3 Tage laufen lassen | Angebote aller 3 Portale kommen an. Die offenen Punkte 1–8 aus Abschnitt 14 sind geklärt. |
| **2 – Kern & Sync** | Projektstruktur, Paket `immo/`, Konfiguration samt Pydantic-Prüfung, `fredy_client`, `sync` mit `fetch_filter`, eigene DB (WAL), Preisverlauf | `sync` lässt sich beliebig oft ausführen, ohne doppelte Einträge. Der Filter wirkt nachweisbar. |
| **3 – Extraktion** | `parse_attrs`, Schema MFH, `pending`/`save`, erste SKILL.md, manueller Testlauf in Codex | Für ≥ 80 % der Testangebote mit Mietangabe wird die Ist-Miete korrekt erkannt. |
| **4 – Scoring & Finanzen** | KPI-Register, Normalisierung, Ausschlusskriterien, Score-Formel, Finanzrechner `finance.simulate()`, **Kaufpreisempfehlung** inkl. Sonderfälle und Zinsspanne, Tests | Ranking und Kaufpreisempfehlung stimmen mit einer Handrechnung für 5 Beispielangebote überein. Beim empfohlenen Preis ergibt die Rechnung exakt den Ziel-Cashflow. |
| **5 – Benachrichtigung & Digest** | `notify` (Telegram, SMTP), Digest-Vorlage, Modi `run` und `digest` | Ein kompletter Lauf liefert Telegram-Meldungen und eine Digest-Mail. |
| **6 – Automatisierung** | `run.ps1`, Windows-Aufgabenplanung, Sperre, Berechtigungen, gespeicherte ChatGPT-Anmeldung, Backup, Überwachung | Läuft eine Woche unbeaufsichtigt ohne Eingriff. |
| **7 – Server: Lesen** | `immo-server` mit Login, Übersicht, Liste, Detailansicht. MCP mit allen Lese-Werkzeugen, Tailscale-Zugang, Links in Telegram/Digest | Oberfläche ist zu Hause und unterwegs per VPN nutzbar. Codex CLI/Desktop beantwortet Fragen wie „Top 5 MFH über 6 %?“ über MCP. |
| **8 – Server: Aktionen** | Status-Workflow & Notizen, Job-Runner (Lauf, Neu auswerten, Digest), Ranking-Simulation, Konfigurations-Editor mit Prüfung, Diff, Backup und Neuberechnung. MCP-Schreib-Werkzeuge | Alle Aktionen funktionieren in Oberfläche und MCP, jede Änderung ist protokolliert. Eine Konfigurationsänderung in der Oberfläche führt zu korrekt neu berechneten Scores und Kaufpreisempfehlungen. |
| **8b – Objekt-Simulation** | Eigene Seite je Angebot und Profil: Kauf, Miete, Finanzierung und Kosten ändern, Jahr-1-Kennzahlen und Score neu rechnen. Zielwert-Rückrechnung (Cashflow, Bruttorendite, Nettoanfangsrendite → Kaufpreis, Miete, Zins, Eigenkapital) über `finance.loese()`. Szenarien in Tabelle `scenario` (speichern, laden, umbenennen, löschen, bis zu 3 vergleichen), Liste in der Detailansicht. Kein MCP | Ohne Änderungen stimmt die Simulation exakt mit der Detailansicht überein. Jede Rückrechnung ergibt eingesetzt in `simulate()` exakt den Zielwert (3 Handrechnungen + Zufallsfälle), nicht erreichbare Ziele werden gemeldet. Szenarien lassen sich speichern, vergleichen und löschen, Score und Ranking bleiben unverändert. |
| **8c – Steuern (vereinfacht)** | Cashflow nach Steuern für Jahr 1 (5.7): AfA, Einkünfte, Steuer; KPI `cashflow_nach_steuern`; Anzeige in Detailansicht, Simulation (Gebäudeanteil und AfA-Satz änderbar) und Vergleich | Handrechnung in `tests/test_finance.py` stimmt; Score und Kaufpreisempfehlung unverändert vor Steuern |
| **9 – Ausbau** (optional) | Karte (Leaflet/OSM), Lernen aus deinem Status-Verlauf (Gewichte vorschlagen), weitere KPIs (Mietpotenzial mit Mietspiegel), weitere Portale/Profile. Aus 8b verschoben: Mehrjahresverlauf, Zinsbindung/Anschlusszins, zweites Darlehen, Steuern über Jahr 1 hinaus, IRR, Sensitivität (Tornado), Leerstand/Zielmiete mit Zeitpunkt, MCP `simulate_listing`/`get_scenarios` | nach Bedarf |

> Die Phasen 7–8 bauen auf der DB aus den Phasen 2–4 auf. Mit einfachen Ansichten kann Phase 7 auch parallel zu 5–6 entstehen.

### 13.1 Stand der Umsetzung (03.11.2026)

- **Formatfehler korrigiert:** Ein fehlerhaftes wert_json verwirft nicht mehr alle Ergebnisse. Gültige Angebote werden gespeichert; nur betroffene Angebote erhalten einen Korrekturversuch. Fehlerstatus, Rohantwort und konkrete Feldmeldung bleiben erhalten. Originalantwort von job-7 auf DB-Kopie nachgespielt: nur Angebot 58 korrigiert, alle vier Ergebnisse angenommen. 181 Tests grün; Details docs/SERVER.md Abschnitt 8.3.

- **Korrektur Web-Lauf:** Codex wird auch ohne Desktop-PATH in lokalen Windows-Installationsordnern gesucht; `ki.cli_pfad` erlaubt eine explizite Auswahl. CLI-Ursachen werden im Job-Log angezeigt. Test ohne Codex im PATH: run.ps1-Neuauswertung und Bewertung Exit 0; 178 Tests grün. Details: docs/SERVER.md Abschnitt 8.2.

- **KI-Migration:** Codex mit ChatGPT-Anmeldung ersetzt Claude Code als KI im Lauf. Python steuert Stapel, Validierung und Speicherung (`ki_io.py`, `codex_extraktion.py`, `scripts/extract.py`). Ressourcen unter `resources/`; DB v3 erlaubt `openai` neben historischen `claude`-Werten und protokolliert neue Extraktionen. Kontingente und Zeitlimit führen zum Teilfehler bei fortgesetzter Bewertung. Modell und Stapelgrenzen unter `settings.ki`. Produktiv-DB nach Backup auf v3 migriert und Server gestartet; Phase-6-Beobachtung bleibt offen. 172 Tests grün.


| Phase | Stand | Nachweis / Anmerkung |
|---|---|---|
| 1 | **fast fertig** | Fredy 29.3.0 läuft auf dem Mini-PC (Windows 11, Docker Desktop). Datierte Ergebnisse in `docs/SETUP-MINIPC.md`. Immowelt beim Ersttest blockiert (Bot-Schutz); erneute Portalprüfung und Fredy-Aufbewahrung ab 01.11.2026 noch offen. Keine erneute Phase-1-Abnahme bei der KI-Migration. |
| 2 | fertig | Tests: Sync idempotent, URL-Normalisierung, `fetch_filter` je Profil, Preisverlauf, entfernt/reaktiviert, fehlerhafter Job markiert nichts als entfernt. Gegen das echte Fredy geprüft (48 Angebote); Duplikate über Portale (`duplicates.py`). |
| 3 | fertig | Historische Abnahme vor dem Wechsel (Claude): Ist-Miete 10/10 korrekt, alle 45 erwarteten Werte stimmen. Mit 48 echten Anzeigen: Ist-Miete bei 21 von 22 Anzeigen mit Mietangabe erkannt (95 %). |
| 4 | fertig | 5 Beispiele gegen Handrechnung (`tests/test_finance.py`). Ziel-Cashflow beim empfohlenen Preis exakt, 500 Zufallsfälle. |
| 5 | offen | Telegram, E-Mail-Digest, `send_digest_now`, Digest-Button. Danach hängt sich der Telegram-Alarm an die Health-Prüfung. |
| 6 | umgesetzt, Abnahme offen | `run.ps1` (Sync → Regeln → `scripts/extract.py` → Codex → Bewertung → Health), `settings.ki` für Modell und Zeitlimit; keine Claude-Berechtigungsdatei mehr. `scripts/install_tasks.ps1` legt drei Aufgaben an: Läufe nach `schedule.run` (über `scripts/lauf.py` als Job „zeitplan“), tägliches Backup, Server bei Anmeldung mit Neustart nach Absturz (`scripts/aufgabe.ps1`). Backup (`backup.py`): `immo.db` per SQLite-Backup-API, `config/`, Fredys DB als geprüfter Schnappschuss, Aufbewahrungsfrist. Health (`health.py`): Portale, Sync, Backup, `/health` → `run_log`. Tests `test_backup.py`, `test_health.py`, `test_jobs_direkt.py`; Backup und Health am echten Bestand geprüft (Kopie). Aufgaben richtet der Nutzer ein (docs/SERVER.md, Abschnitt 7), danach eine Woche beobachten. Lauf von Hand am 19.10.2026: Exit 0, 3 neue Angebote ausgewertet. Letzter Aufgabencheck am 20.10.2026: noch nicht eingerichtet; bei der KI-Migration keine Aufgaben geändert. |
| 7 | fertig (ohne Telegram/Digest-Links) | `immo-server` mit Login, Übersicht, Liste, Detail; MCP mit allen Lese-Werkzeugen. Tests `tests/test_server.py`, im Browser und per MCP am echten Bestand geprüft. Tailscale-Zugang: Anleitung `docs/SERVER.md`, noch nicht eingerichtet. |
| 8 | fertig (ohne Digest) | Status-Workflow, Notizen, Job-Runner (Lauf, Neu auswerten, Bewerten), Ranking-Simulation mit Übernahme ins Profil, Konfigurations-Editor (Prüfung, Diff, Backup, Protokoll, Neuberechnung, Profile kopieren/aktivieren), MCP-Schreib-Werkzeuge. |
| 8b | fertig (19.10.2026, Umfang verkleinert) | `finance.loese()` (geschlossene Formeln), `objekt_simulation.py` (Basis wie `scoring.bewerte`, Formular, Szenarien), Seiten `/angebot/<id>/simulation` und `/angebot/<id>/vergleich`, Szenarien in der Detailansicht. Tests `tests/test_objekt_simulation.py`: 8 Handrechnungen, 1 500 Zufallsfälle (Zielwert exakt getroffen), ohne Änderung = gespeicherte Bewertung, Szenarien ändern keine Bewertung. Im Browser mit einer Kopie des echten Bestands geprüft (Angebot 24: Break-even-Zins 4,01 %, Kaufpreis für Cashflow 0 = Empfehlung). |
| 8c | fertig (20.10.2026) | Steuern vereinfacht (5.7). Tests: 2 Handrechnungen (Verlust → Ersparnis, Gewinn, Tilgung nicht absetzbar) und Simulation (Gebäudeanteil/AfA übersteuert). Angebot 24 in der DB-Kopie: AfA 23 266 €, Ersparnis 5 740 €, Cashflow −899 → −420 €/Monat nach Steuern. |
| 9 | offen | optional |

Commits: `f62f8b2` (Phasen 2+3), `8a5989d` (Phase 4), `4bc6e12` (Vorbereitung Phase 1), `83c1df9` (Phasen 7+8), `e1969a9` (Phase 6), `d6549f0` (Phase 8b).

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
5. **Duplikate über Portale:** Liefert Fredy eine Duplikat-Kennung? In der Tabelle `listings` ist keine zu sehen. Bis das geklärt ist, bildet jedes Angebot seine eigene `duplicate_group`. Sonst eine eigene Erkennung (Adresse/Koordinaten + Fläche + Preis) in `sync`. **Geklärt 18.10.2026:** Fredy liefert keine Kennung; umgesetzt in `duplicates.py` (gleiche PLZ, Titel ≥ 90 % ähnlich, Preis ± 5 %, Fläche ± 2 %, verschiedene Portale).
6. **Objektart in den Daten:** Kann `sync` die Objektart und den Job je Angebot sicher zuordnen? Davon hängt die Zuordnung zum Profil ab.
7. **Ortsdaten:** Sind PLZ und Koordinaten in Fredy-Daten verlässlich vorhanden? Sonst werden sie per Geocoding (OSM/Nominatim, sparsam und zwischengespeichert) ergänzt.
8. **Codex ohne Oberfläche:** Anmeldung im gleichen Windows-Konto und echte Neuauswertung am 03.11.2026 geprüft. Noch offen: Aufgabenplanung bei gesperrtem Bildschirm und eine Woche unbeaufsichtigter Betrieb. Bei Nutzungslimit oder CLI-Fehler bleibt die Bewertung aktiv; tatsächliches Kontingentverhalten im Dauerbetrieb beobachten.

**In Phase 7 prüfen:**

9. **MCP-Anbindung:** Codex CLI über HTTP und `MCP_TOKEN`-Umgebungsvariable einrichten; Zugriff vom tatsächlichen Client über LAN/Tailscale noch abnehmen. ChatGPT Web braucht eine separat geprüfte Erreichbarkeit.
10. **Job-Runner:** startet `run.ps1` → Python → `codex exec`. Neuauswertung mit Bewertung auf Test-DB und Weitergabe von DB/Konfiguration geprüft (03.11.2026); unbeaufsichtigte Abnahme bleibt offen.

---

## 15. Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| IS24-App-Schnittstelle (inoffiziell) fällt weg | Überwachung je Portal, kurzfristig E-Mail-Suchagent als Reserve, auf Fredy-Updates warten |
| Fredy wird nur von einer Person gepflegt | Festes Image-Tag, Zugriff auf Fredy in `fredy_client` kapseln, damit sich die Quelle austauschen lässt |
| Fredy-Update ändert API oder Schema | Fester Tag, Vertragstests in `tests/`, Update erst nach Test |
| Codex extrahiert falsch | Belegstelle Pflicht, Schema-Prüfung, Quelle und Konfidenz in Detailansicht und Digest sichtbar, „Neu auswerten“ per Klick |
| Mietangaben fehlen oft | Als „unvollständig“ markieren statt verwerfen. Optional Schätzung, deutlich gekennzeichnet. |
| SQLite-Sperrkonflikte (Server liest, Lauf schreibt) | WAL-Modus, `busy_timeout`, kurze Transaktionen, nur ein schreibender Lauf gleichzeitig, Server läuft auf demselben Dateisystem (nicht in Docker) |
| Fehlerhafte Konfiguration über die Oberfläche | Pydantic-Prüfung, Diff-Vorschau, Backup vor jedem Speichern, Wiederherstellung in der Oberfläche |
| Unbefugter Zugriff auf Oberfläche/MCP | Kein Internetzugang (nur LAN + Tailscale), Login + CSRF, eigenes MCP-Token, Schreib-Werkzeuge einzeln abschaltbar |
| Codex stößt über MCP zu viele Läufe an | Sperre + Warteschlange, identische offene Jobs werden zusammengefasst, alles in `job` protokolliert; kein konfigurierbarer Mindestabstand umgesetzt |
| Mini-PC aus oder Update-Neustart | Autostart von Docker, Server und Tailscale, Ruhezustand aus, Neustart-Fenster für Windows Update festlegen, Alarm bei fehlendem Lauf |
| Kontingent erschöpft | Nur neue Angebote auswerten, kompakte Eingabe, Lauf bricht sauber ab und setzt beim nächsten Mal fort |

---

## 16. Rechtliches & Datenschutz (Hinweis, keine Rechtsberatung)

- Nur private, nicht-kommerzielle Nutzung, keine Weitergabe oder Veröffentlichung der Daten
- Moderate Abrufhäufigkeit, keine Umgehung von Schutzmechanismen
- Fredys Lizenz (Apache 2.0 + Commons Clause) erlaubt die private Nutzung, verbietet aber den Verkauf
- Die eigene Datenbank bleibt lokal. Die KI-Extraktion übermittelt Titel, Beschreibungsauszüge und ausgewählte Objektdaten an OpenAI; eine automatische Entfernung von Namen oder Telefonnummern aus diesen Texten ist nicht implementiert. Die Oberfläche ist nicht öffentlich; der geplante Digest ist nur für den Nutzer vorgesehen.

## 17. Verifizierte KI-Umstellung (03.11.2026)

Dieser Abschnitt ersetzt die Codex-Code-spezifischen Betriebsangaben und Pfade im ursprünglichen Entwurf.
Abnahme 03.11.2026: 172 Tests grün; vier echte Codex-Testauswertungen ohne Ablehnung sowie run.ps1-Neuauswertung
mit anschließender Bewertung und Exit 0. Produktiv-DB vor Migration gesichert, auf v3 migriert (368 Werte erhalten), Server gestartet.
`run.ps1` startet `scripts/extract.py`; die Fachlogik liegt in `src/immo/codex_extraktion.py` und `ki_io.py`.
Codex wird mit gespeicherter ChatGPT-Anmeldung, isoliert und mit strukturierter JSON-Ausgabe aufgerufen.
Die Fachschemata bleiben Version 1; nur die DB steigt auf Version 3. Der Wechsel selbst löst keine erneute Auswertung aus.
Fachregeln und Schema liegen unter `resources/`; `.claude/run-settings.json` wird nicht mehr verwendet.
MCP-Clients können Codex nutzen; die Server-Werkzeuge bleiben kompatibel. Digest bleibt Phase 5.
Einzelheiten zu Konfiguration, Logs, Migration und Rückkehr zum alten Stand: docs/SERVER.md, Abschnitt 8.
