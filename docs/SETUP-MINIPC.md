# Phase 1 – Fredy auf dem Mini-PC einrichten

Ziel: Fredy läuft rund um die Uhr in Docker, sammelt Mehrfamilienhäuser von ImmoScout24, Immowelt und Kleinanzeigen, und `scripts/check_fredy.py` beantwortet die offenen Punkte aus PLAN.md, Abschnitt 14.

Zeitaufwand: ca. 1–2 Stunden Einrichtung, danach 2–3 Tage laufen lassen.

---

## 1. Windows vorbereiten

| Einstellung | Wo | Wert |
|---|---|---|
| Energiesparen / Ruhezustand | Einstellungen → System → Netzbetrieb und Akku | Bildschirm aus nach 10 Min., **Standby: Nie**, Ruhezustand aus |
| Automatische Anmeldung | `netplwiz` (bzw. Sysinternals *Autologon*) | Benutzer automatisch anmelden. Docker Desktop läuft nur in einer angemeldeten Sitzung. |
| Bildschirm sperren nach Anmeldung | Aufgabenplanung: Aufgabe „bei Anmeldung“ → `rundll32.exe user32.dll,LockWorkStation` | damit der Rechner nach dem Autologin nicht offen dasteht |
| Windows Update | Einstellungen → Windows Update → Erweiterte Optionen → Nutzungszeit | z. B. 06:00–23:00, Neustarts nur nachts |

> Mit Autologon (Sysinternals) liegt das Passwort verschlüsselt in der Registry statt im Klartext. Das ist der sicherere Weg.

## 2. Docker Desktop installieren

```powershell
winget install -e --id Docker.DockerDesktop
```

Danach neu anmelden und Docker Desktop starten:

- **Settings → General:** „Start Docker Desktop when you sign in“ einschalten. Das WSL-2-Backend ist Standard.
- **Settings → Resources:** 2–4 GB RAM reichen. Für Immowelt und Kleinanzeigen startet Fredy einen Headless-Browser.

Prüfen:

```powershell
docker version
```

## 3. Projekt klonen und Fredy starten

```powershell
git clone <repo-url> C:\E\ai-workspace\immo-search
cd C:\E\ai-workspace\immo-search
powershell -ExecutionPolicy Bypass -File docker\fredy\setup.ps1
```

`setup.ps1` legt `C:\E\docker\fredy\conf` und `C:\E\docker\fredy\db` an, startet den Container (fester Image-Tag, `restart: unless-stopped`) und wartet, bis die Oberfläche unter http://localhost:9998 antwortet.

> **LAN-Zugriff:** Die Compose-Datei bindet Fredy nur an `127.0.0.1`. Das reicht, weil `immo-search` auf demselben Rechner läuft. Fredys Oberfläche brauchst du nur zur Fehlersuche (z. B. per Remote Desktop).

## 4. Fredy absichern und einstellen

Öffne http://localhost:9998 und melde dich mit `admin` / `admin` an.

1. **Passwort ändern** (Benutzerverwaltung). Danach in `C:\E\ai-workspace\immo-search\.env` eintragen:
   ```
   FREDY_USERNAME=admin
   FREDY_PASSWORD=<neues Passwort>
   ```
2. **Analytics:** Fragt Fredy nach der Zustimmung zu Analytics, ablehnen. Später in den Einstellungen prüfen, dass sie aus ist.
3. **Onboarding-Tour:** Falls sie startet, durchklicken oder überspringen. Den Demo-Job mit Düsseldorf-Beispielen löscht Fredy danach selbst.
4. **Administration → Execution:** Intervall **60 Minuten**, wenn möglich nur 07–22 Uhr. Seltener abzufragen schont die Portale. Häufiger lohnt sich nicht, weil `sync` ohnehin nur alle 3 Stunden läuft.
5. **Benachrichtigungen:** **keine** Notification-Channels an die Jobs hängen. Melden übernimmt später `immo-search` (Telegram/E-Mail), sonst kommen Meldungen doppelt.

## 5. Such-URLs und Jobs anlegen

Für jedes Portal: Suche im Browser einstellen, **nach Datum sortieren (neueste zuerst)**, URL kopieren und in Fredy als Provider eines Jobs eintragen.

Die **Job-Namen** müssen genau zu `fredy.jobs` im Profil passen ([config/profiles/mfh-beispiel.yaml](../config/profiles/mfh-beispiel.yaml)), z. B.:

| Job-Name in Fredy | Portal | Suche |
|---|---|---|
| `MFH Region X – IS24` | ImmoScout24 | siehe unten |
| `MFH Region X – Immowelt` | Immowelt | Häuser kaufen → Haustyp Mehrfamilienhaus, Region, Preis |
| `MFH Region X – Kleinanzeigen` | Kleinanzeigen | Immobilien → Häuser zum Kauf, Region + Umkreis, Suchbegriff „Mehrfamilienhaus“ |

Alternativ alle Jobs mit demselben Präfix benennen und im Profil `job_prefix: "MFH Region X"` setzen. Gedankenstriche (–) und Bindestriche (-) sind verschiedene Zeichen, am besten den Namen aus Fredy kopieren.

**ImmoScout24 (offener Punkt 4):** Fredy unterstützt bei IS24 Wohnungen, Häuser, Grundstücke usw., **aber keine gewerblichen Suchen**. Mehrfamilienhäuser gibt es bei IS24 an zwei Stellen. Bitte beide testen:

1. **Haus kaufen → Haustyp „Mehrfamilienhaus“** – sollte funktionieren.
2. **Anlageobjekte → Mehrfamilienhaus** – meldet wahrscheinlich *„Real estate type not found“* im Fredy-Log.

Was funktioniert, kommt in die Tabelle unten. Das Log zeigst du mit:

```powershell
docker logs fredy --tail 100
```

Fredy protokolliert auch Filter, die es aus der URL nicht übernehmen kann. Die Suche läuft dann breiter. Das ist unkritisch, weil `fetch_filter` in `immo-search` genauer filtert.

**Profil anpassen:** In `config/profiles/mfh-beispiel.yaml` die Platzhalter ersetzen: PLZ/Orte, Preis, Bundesland, Eigenkapital. Danach prüfen:

```powershell
uv sync
uv run pytest -q
```

## 6. Erster Abgleich (sofort)

```powershell
uv run python scripts/check_fredy.py
```

Das Skript fragt Fredy ab, **ohne** in `data/immo.db` zu schreiben, und meldet:

- ob Login, Job-Liste und Angebotsabruf funktionieren (offener Punkt 1)
- ob die Job-Namen der Profile in Fredy gefunden werden
- je Job: Anzahl Angebote, Portale, Abdeckung der Felder (Preis, Fläche, Adresse, PLZ, Koordinaten, Beschreibung), Länge der Beschreibungen (Punkte 3, 6, 7)
- welche Rohfelder Fredy liefert und welche der Client nicht abbildet
- mögliche Duplikate über Portale und ob Fredy eine Duplikat-Kennung liefert (Punkt 5)
- wie oft die Regeln schon eine Ist-Miete finden

Eine Stichprobe der Rohdaten landet in `data/fredy_check/` (nicht im Git). Diese Datei und die Ausgabe brauche ich, um den Client anzupassen.

## 7. 2–3 Tage laufen lassen, dann

```powershell
uv run python scripts/check_fredy.py
uv run python scripts/sync.py
```

- **Punkt 2 (Erstbefüllung):** Vergleich der Anzahl von Tag 1 und Tag 3. Kamen am ersten Tag nur wenige Angebote, obwohl die Portalsuche viele zeigt, speichert Fredy nur neue. Dann den Job in Fredy löschen und neu anlegen bzw. auf ein Zurücksetzen prüfen.
- `sync.py` zweimal hintereinander ausführen. Beim zweiten Mal muss `neu` = 0 sein.

## 8. Ergebnisse festhalten

| Punkt | Ergebnis | Datum |
|---|---|---|
| 1 Fredy-API (Login, Felder) | ok. Felder = DB-Spalten (snake_case), `created_at` = Epoch-ms als Text. Job-Filter heißt `jobNameFilter` (Wert = Job-ID), `jobIdFilter` wird ignoriert – im Client korrigiert. | 18.10.2026 |
| 2 Erstbefüllung | Erster Lauf holt den ganzen Bestand (IS24 26, Kleinanzeigen 23). | 18.10.2026 |
| 3 Details je Portal (Beschreibung vollständig?) | Ohne Detailabruf nein: IS24 leer, Kleinanzeigen nach ~100 Zeichen abgeschnitten. Benutzereinstellung `provider_details` = `[immoscout, immowelt, kleinanzeigen]` gesetzt, Bestand per `POST /api/listings/:id/details` nachgeladen (49/49). Danach Median IS24 2 774, Kleinanzeigen 3 176 Zeichen, nichts mehr abgeschnitten. Regeln finden Ist-Miete: IS24 42 %, Kleinanzeigen 9 %. | 18.10.2026 |
| 4 IS24-Such-URL für MFH | `Suche/radius/mehrfamilienhaus-kaufen?geocoordinates=…` funktioniert. Fredy 29.3 kann auch `anlageimmobilie`. | 18.10.2026 |
| 5 Duplikate über Portale | Keine Kennung von Fredy. Eigene Erkennung in `duplicates.py` (PLZ + Titel + Preis + Fläche): 7 Paare IS24/Kleinanzeigen, keine Fehltreffer. | 18.10.2026 |
| 6 Zuordnung Objektart/Job | ein Job je Portal, Profil über `job_prefix: "MFH KL"` | 18.10.2026 |
| 7 PLZ/Koordinaten | PLZ 100 %. Koordinaten: IS24 23 %, Kleinanzeigen 100 %. Baujahr 0 %. | 18.10.2026 |
| Immowelt | Erster Lauf: Bot erkannt (HTTP 403), 0 Angebote. Beobachten. | 18.10.2026 |
| 8 Claude ohne Oberfläche (Phase 6) | | |

Phase 1 ist fertig, wenn alle drei Portale Angebote liefern und die Punkte 1–7 hier eingetragen sind. Punkt 8 klärt sich mit `run.ps1` in Phase 6.
