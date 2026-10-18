"""Ranking-Simulation: Profilwerte im Speicher ändern und mit derselben Bewertungslogik neu rechnen.

Es wird nichts gespeichert. `als_yaml()` erzeugt aus denselben Änderungen den neuen Profiltext
(Kommentare bleiben erhalten), den der Konfigurations-Editor dann prüft und speichert.

Änderungen (alle optional):
    gewichte          {kpi: Gewicht}
    normalisierung    {kpi: {"min": x, "max": y}}
    ausschluss        {Index in hard_filter: neuer Schwellwert}
    finanzen          {Feld aus finance: Wert}
    ziel_cashflow_monat, tilgung_einrechnen
"""

from __future__ import annotations

import copy
import sqlite3
from typing import Any

from pydantic import ValidationError

from .config import Config, FinanceAssumptions, Profile
from .config_edit import lesen, setze_werte
from .extraction import field_values
from .scoring import bewerte, pruefe_profil, ranking

FINANZ_FELDER = tuple(FinanceAssumptions.model_fields)


class SimulationsFehler(ValueError):
    pass


def _zahl(v: Any, name: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError) as exc:
        raise SimulationsFehler(f"{name}: keine Zahl ({v!r})") from exc


def wert_wie(alt: Any, wert: Any, name: str) -> Any:
    """Neuen Schwellwert in den Typ des alten umwandeln (Ja/Nein, Zahl, Text)."""
    if isinstance(alt, bool):
        if isinstance(wert, bool):
            return wert
        s = str(wert).strip().lower()
        if s in ("true", "ja", "1", "wahr"):
            return True
        if s in ("false", "nein", "0", "falsch"):
            return False
        raise SimulationsFehler(f"{name}: ja/nein erwartet ({wert!r})")
    if isinstance(alt, list):
        if not isinstance(wert, list):
            raise SimulationsFehler(f"{name}: Liste erwartet")
        return wert
    if isinstance(alt, str):
        return str(wert)
    z = _zahl(wert, name)
    return int(z) if isinstance(alt, int) and z.is_integer() else z


def wende_an(profile: Profile, aenderungen: dict[str, Any]) -> Profile:
    data = copy.deepcopy(profile.model_dump(mode="python"))
    for kpi, w in (aenderungen.get("gewichte") or {}).items():
        if kpi not in data["scoring"]["kpis"]:
            raise SimulationsFehler(f"KPI '{kpi}' ist im Profil nicht konfiguriert")
        data["scoring"]["kpis"][kpi]["weight"] = _zahl(w, f"Gewicht {kpi}")
    for kpi, grenzen in (aenderungen.get("normalisierung") or {}).items():
        if kpi not in data["scoring"]["kpis"]:
            raise SimulationsFehler(f"KPI '{kpi}' ist im Profil nicht konfiguriert")
        for k in ("min", "max"):
            if grenzen.get(k) is not None:
                data["scoring"]["kpis"][kpi]["normalize"][k] = _zahl(grenzen[k], f"{kpi}.{k}")
    for idx, wert in (aenderungen.get("ausschluss") or {}).items():
        i = int(idx)
        if not 0 <= i < len(data["hard_filter"]):
            raise SimulationsFehler(f"Ausschlusskriterium {i} gibt es nicht")
        if wert is not None:
            alt = data["hard_filter"][i]["value"]
            data["hard_filter"][i]["value"] = wert_wie(alt, wert, data["hard_filter"][i]["field"])
    for feld, wert in (aenderungen.get("finanzen") or {}).items():
        if feld not in FINANZ_FELDER:
            raise SimulationsFehler(f"Unbekannte Finanzannahme '{feld}'")
        data["finance"][feld] = wert
    if aenderungen.get("ziel_cashflow_monat") is not None:
        data["kaufpreisempfehlung"]["ziel_cashflow_monat"] = _zahl(aenderungen["ziel_cashflow_monat"], "Ziel-Cashflow")
    if aenderungen.get("tilgung_einrechnen") is not None:
        data["kaufpreisempfehlung"]["tilgung_einrechnen"] = bool(aenderungen["tilgung_einrechnen"])
    try:
        neu = Profile.model_validate(data)
    except ValidationError as exc:
        raise SimulationsFehler("; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())) from exc
    pruefe_profil(neu)
    return neu


def simuliere_ranking(conn: sqlite3.Connection, config: Config, profil_id: str, aenderungen: dict[str, Any], limit: int = 50) -> dict[str, Any]:
    if profil_id not in config.profiles:
        raise SimulationsFehler(f"Profil '{profil_id}' nicht gefunden")
    neu_profil = wende_an(config.profiles[profil_id], aenderungen)
    neu_cfg = config.model_copy(update={"profiles": {**config.profiles, profil_id: neu_profil}})

    alt = ranking(conn, config, profil_id)
    rang_alt = {r["id"]: i + 1 for i, r in enumerate(alt)}
    alt_by_id = {r["id"]: r for r in alt}

    rows = conn.execute(
        """SELECT l.* FROM listing l JOIN listing_profile lp ON lp.listing_id = l.id
           WHERE lp.profile_id = ? AND l.status_portal = 'aktiv'""", (profil_id,)).fetchall()
    ergebnisse = []
    for row in rows:
        b = bewerte(neu_cfg, neu_profil, dict(row), field_values(conn, row["id"]))
        ergebnisse.append((row, b))
    bestanden = sorted((e for e in ergebnisse if not e[1].ausgeschlossen and e[1].score is not None),
                       key=lambda e: (-e[1].score, e[0]["id"]))
    gesehen: set[int] = set()
    neu_rang: list[tuple[sqlite3.Row, Any]] = []
    for row, b in bestanden:
        g = row["duplicate_group"] or row["id"]
        if g not in gesehen:
            gesehen.add(g)
            neu_rang.append((row, b))

    zeilen = []
    for i, (row, b) in enumerate(neu_rang[:limit], start=1):
        a = alt_by_id.get(row["id"])
        zeilen.append({
            "id": row["id"], "titel": row["titel"], "ort": row["ort"], "preis": row["preis"],
            "rang_neu": i, "rang_alt": rang_alt.get(row["id"]),
            "veraenderung": None if row["id"] not in rang_alt else rang_alt[row["id"]] - i,
            "score_neu": b.score, "score_alt": a["score"] if a else None,
            "kpe_neu": b.kaufpreisempfehlung, "kpe_alt": a["kaufpreisempfehlung"] if a else None,
            "preisabstand_neu": b.preisabstand,
        })
    neu_ids = {row["id"] for row, _ in neu_rang}
    ausgeschieden = [{"id": r["id"], "titel": r["titel"], "rang_alt": rang_alt[r["id"]]}
                     for r in alt if r["id"] not in neu_ids]
    grund = {}
    for row, b in ergebnisse:
        if b.ausgeschlossen:
            k = (b.ausschlussgrund or "").split(" ")[0]
            grund[k] = grund.get(k, 0) + 1
    return {"profil": profil_id, "aenderungen": aenderungen, "anzahl_alt": len(alt), "anzahl_neu": len(neu_rang),
            "ranking": zeilen, "ausgeschieden": ausgeschieden, "ausschlussgruende": grund}


def als_yaml(config: Config, profil_id: str, aenderungen: dict[str, Any]) -> tuple[str, str]:
    """(rel, neuer Text) des Profils mit den simulierten Änderungen."""
    profil = config.profiles[profil_id]
    wende_an(profil, aenderungen)  # prüft
    werte: dict[tuple, Any] = {}
    for kpi, w in (aenderungen.get("gewichte") or {}).items():
        werte[("scoring", "kpis", kpi, "weight")] = float(w)
    for kpi, grenzen in (aenderungen.get("normalisierung") or {}).items():
        for k in ("min", "max"):
            if grenzen.get(k) is not None:
                werte[("scoring", "kpis", kpi, "normalize", k)] = float(grenzen[k])
    for idx, wert in (aenderungen.get("ausschluss") or {}).items():
        if wert is not None:
            regel = profil.hard_filter[int(idx)]
            werte[("hard_filter", int(idx), "value")] = wert_wie(regel.value, wert, regel.field)
    for feld, wert in (aenderungen.get("finanzen") or {}).items():
        werte[("finance", feld)] = wert
    if aenderungen.get("ziel_cashflow_monat") is not None:
        werte[("kaufpreisempfehlung", "ziel_cashflow_monat")] = float(aenderungen["ziel_cashflow_monat"])
    if aenderungen.get("tilgung_einrechnen") is not None:
        werte[("kaufpreisempfehlung", "tilgung_einrechnen")] = bool(aenderungen["tilgung_einrechnen"])
    rel = f"profiles/{profil_id}.yaml"
    return rel, setze_werte(lesen(config.config_dir, rel), werte)
