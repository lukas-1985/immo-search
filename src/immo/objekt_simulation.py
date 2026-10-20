"""Objekt-Simulation (Phase 8b): ein Angebot mit geänderten Annahmen für Jahr 1 durchrechnen, Zielwerte zurückrechnen, Szenarien.

Ausgangspunkt ist immer dieselbe Herleitung wie in der Bewertung (`scoring.basis_annahmen`), gerechnet wird mit
`finance.simulate()` und `scoring.bewerte()`. Ohne Änderungen kommen also exakt die Werte der Detailansicht heraus.
Szenarien speichern nur die geänderten Parameter und ändern weder Score noch Ranking noch Profil.
Bewusst kein MCP (Entscheidung 19.10.2026).
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from .config import Config, Profile
from .db import now_iso
from .extraction import field_values
from .finance import ZIEL_GROESSEN, Annahmen, Ergebnis, Loesung, loese, simulate
from .scoring import Bewertung, basis_annahmen, bewerte


class ObjektFehler(ValueError):
    pass


@dataclass(frozen=True)
class Parameter:
    name: str
    label: str
    gruppe: str
    art: Literal["eur", "pct", "zahl", "bool", "ek"]


PARAMETER: tuple[Parameter, ...] = (
    Parameter("kaufpreis", "Kaufpreis", "Kauf", "eur"),
    Parameter("makler", "Makler", "Kauf", "pct"),
    Parameter("sanierung_sofort", "Sanierung sofort", "Kauf", "eur"),
    Parameter("miete_ist", "Jahresnettokaltmiete", "Miete", "eur"),
    Parameter("wohnflaeche", "Wohnfläche (m²)", "Miete", "zahl"),
    Parameter("eigenkapital", "Eigenkapital", "Finanzierung", "ek"),
    Parameter("zins", "Zins", "Finanzierung", "pct"),
    Parameter("tilgung", "Tilgung", "Finanzierung", "pct"),
    Parameter("tilgung_einrechnen", "Tilgung einrechnen", "Finanzierung", "bool"),
    Parameter("bewirtschaftung_quote", "Bewirtschaftung (Anteil der Miete)", "Kosten und Ziel", "pct"),
    Parameter("instandhaltung_eur_m2_jahr", "Instandhaltung (€/m² und Jahr)", "Kosten und Ziel", "eur"),
    Parameter("ziel_cashflow_monat", "Ziel-Cashflow (€/Monat)", "Kosten und Ziel", "eur"),
    Parameter("gebaeudeanteil", "Gebäudeanteil (an Kaufpreis + Nebenkosten)", "Steuern (vereinfacht)", "pct"),
    Parameter("afa_satz", "AfA-Satz", "Steuern (vereinfacht)", "pct"),
)
PARAM: dict[str, Parameter] = {p.name: p for p in PARAMETER}
GRUPPEN = ("Kauf", "Miete", "Finanzierung", "Kosten und Ziel", "Steuern (vereinfacht)")

ZIELE: dict[str, str] = {
    "cashflow_monat": "Cashflow / Monat (€)",
    "bruttorendite": "Bruttorendite (%)",
    "nettoanfangsrendite": "Nettoanfangsrendite (%)",
}
GROESSEN: dict[str, str] = {"kaufpreis": "Kaufpreis", "miete_ist": "Miete", "zins": "Zins", "eigenkapital": "Eigenkapital"}

# Ergebnis-Kennzahlen: Name → (Bezeichnung, Art); Art steuert Format und Toleranz beim Vergleich
KENNZAHLEN: dict[str, tuple[str, str]] = {
    "nebenkosten": ("Kaufnebenkosten", "eur"),
    "gesamtinvestition": ("Gesamtinvestition", "eur"),
    "darlehen": ("Darlehen", "eur"),
    "rate_monat": ("Rate / Monat", "eur"),
    "cashflow_monat": ("Cashflow / Monat", "eur"),
    "afa_jahr": ("AfA / Jahr", "eur"),
    "einkuenfte_jahr": ("Steuerliches Ergebnis / Jahr", "eur"),
    "steuer_jahr": ("Steuer / Jahr (− = Ersparnis)", "eur"),
    "cashflow_nach_steuern_monat": ("Cashflow nach Steuern / Monat", "eur"),
    "bruttorendite": ("Bruttorendite", "pct"),
    "faktor": ("Faktor", "zahl"),
    "nettoanfangsrendite": ("Nettoanfangsrendite", "pct"),
    "kaufpreisempfehlung": ("Kaufpreisempfehlung", "eur"),
    "kpe_zins_plus": ("Empfehlung bei Zins +0,5 Pp", "eur"),
    "kpe_zins_minus": ("Empfehlung bei Zins −0,5 Pp", "eur"),
    "preisabstand": ("Preisabstand", "pct"),
    "score": ("Score", "zahl"),
}
# Färbung der Abweichung: +1 = mehr ist besser, −1 = weniger ist besser, fehlt = neutral
RICHTUNG: dict[str, int] = {"cashflow_monat": 1, "cashflow_nach_steuern_monat": 1, "steuer_jahr": -1, "bruttorendite": 1, "nettoanfangsrendite": 1, "kaufpreisempfehlung": 1,
                            "kpe_zins_plus": 1, "kpe_zins_minus": 1, "score": 1, "faktor": -1, "preisabstand": -1}
MAX_VERGLEICH = 3
MAX_NAME = 80


# --------------------------------------------------------------------------- Basis


@dataclass
class Basis:
    config: Config
    profile: Profile
    listing: dict[str, Any]
    felder: dict[str, dict]
    annahmen: Annahmen


def lade_basis(conn: sqlite3.Connection, config: Config, listing_id: int, profil_id: str | None = None) -> Basis:
    """Ausgangswerte eines Angebots für ein Profil (ohne Profil-Angabe: das erste zugeordnete)."""
    row = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    if row is None:
        raise ObjektFehler(f"Angebot {listing_id} nicht gefunden")
    zugeordnet = [r["profile_id"] for r in conn.execute(
        "SELECT profile_id FROM listing_profile WHERE listing_id = ? ORDER BY profile_id", (listing_id,))]
    zugeordnet = [p for p in zugeordnet if p in config.profiles]
    if profil_id is None:
        if not zugeordnet:
            raise ObjektFehler(f"Angebot {listing_id} gehört zu keinem Profil")
        profil_id = zugeordnet[0]
    if profil_id not in zugeordnet:
        raise ObjektFehler(f"Angebot {listing_id} gehört nicht zum Profil '{profil_id}'")
    listing = dict(row)
    if not listing.get("preis"):
        raise ObjektFehler("Kaufpreis fehlt – keine Simulation möglich")
    profile = config.profiles[profil_id]
    felder = field_values(conn, listing_id)
    return Basis(config, profile, listing, felder, basis_annahmen(config, profile, listing, felder))


# --------------------------------------------------------------------------- Änderungen prüfen


def _gleich(p: Parameter, a: Any, b: Any) -> bool:
    if p.art in ("bool", "ek") or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return a == b
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9 if p.art == "pct" else 0.005)


def normalisiere(basis: Annahmen, aenderungen: dict[str, Any]) -> dict[str, Any]:
    """Nur gültige, echte Änderungen gegenüber den Ausgangswerten (Reihenfolge wie PARAMETER)."""
    unbekannt = set(aenderungen) - set(PARAM)
    if unbekannt:
        raise ObjektFehler(f"Unbekannte Parameter: {', '.join(sorted(unbekannt))}")
    out: dict[str, Any] = {}
    for p in PARAMETER:
        if p.name not in aenderungen:
            continue
        v = aenderungen[p.name]
        if p.art == "bool":
            v = bool(v)
        elif p.art == "ek" and v == "nebenkosten":
            pass
        else:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ObjektFehler(f"{p.label}: keine Zahl ({v!r})") from None
            if not math.isfinite(v):
                raise ObjektFehler(f"{p.label}: keine gültige Zahl")
            if v < 0 and p.name != "ziel_cashflow_monat":  # nur der Ziel-Cashflow darf negativ sein
                raise ObjektFehler(f"{p.label}: muss ≥ 0 sein")
            if p.name == "kaufpreis" and v <= 0:
                raise ObjektFehler("Kaufpreis muss größer als 0 sein")
            if p.art == "pct" and v > 1:
                raise ObjektFehler(f"{p.label}: höchstens 100 %")
        if not _gleich(p, v, getattr(basis, p.name)):
            out[p.name] = v
    return out


def _kwargs(basis: Annahmen, aenderungen: dict[str, Any]) -> dict[str, Any]:
    """Änderungen → Argumente für `simulate()`; eine selbst gesetzte Miete gilt nicht mehr als Schätzung."""
    kw = dict(aenderungen)
    if "miete_ist" in kw:
        kw["miete_qualitaet"] = "exakt"
        kw["hinweise"] = tuple(h for h in basis.hinweise if not h.startswith("Miete geschätzt"))
    return kw


# --------------------------------------------------------------------------- Rechnen


def kennzahlen(e: Ergebnis, b: Bewertung) -> dict[str, Any]:
    ke = e.kaufpreisempfehlung
    return {
        "nebenkosten": e.nebenkosten, "gesamtinvestition": e.gesamtinvestition, "darlehen": e.darlehen,
        "rate_monat": e.rate_monat, "cashflow_monat": e.cashflow_monat, "afa_jahr": e.afa_jahr,
        "einkuenfte_jahr": e.einkuenfte_jahr, "steuer_jahr": e.steuer_jahr,
        "cashflow_nach_steuern_monat": e.cashflow_nach_steuern_monat, "bruttorendite": e.bruttorendite,
        "faktor": e.faktor, "nettoanfangsrendite": e.nettoanfangsrendite, "kaufpreisempfehlung": ke.preis,
        "kpe_zins_plus": ke.zins_plus, "kpe_zins_minus": ke.zins_minus, "preisabstand": ke.preisabstand,
        "score": b.score, "kpe_status": ke.status, "kpe_text": ke.text, "kpe_qualitaet": ke.qualitaet,
        "ausgeschlossen": b.ausschlussgrund if b.ausgeschlossen else None,
    }


def rechne(basis: Basis, aenderungen: dict[str, Any]) -> dict[str, Any]:
    """Ausgangswert und Simulation nebeneinander; `aenderungen` vorher mit `normalisiere` geprüft."""
    kw = _kwargs(basis.annahmen, aenderungen)
    e0, e1 = simulate(basis.annahmen), simulate(basis.annahmen, **kw)
    b0 = bewerte(basis.config, basis.profile, basis.listing, basis.felder)
    b1 = bewerte(basis.config, basis.profile, basis.listing, basis.felder, kw) if kw else b0
    return {
        "basis": kennzahlen(e0, b0), "simulation": kennzahlen(e1, b1),
        "annahmen_basis": e0.annahmen, "annahmen": e1.annahmen, "aenderungen": aenderungen,
        "hinweise": b1.details.get("hinweise", []),
    }


def loese_ziel(basis: Basis, aenderungen: dict[str, Any], ziel: str, zielwert: float, groesse: str) -> tuple[dict[str, Any], Loesung]:
    """Zielwert-Rückrechnung auf Basis der aktuellen Änderungen; bei Erfolg wird die Lösung als Änderung übernommen."""
    if ziel not in ZIELE or groesse not in ZIEL_GROESSEN[ziel]:
        raise ObjektFehler(f"'{GROESSEN.get(groesse, groesse)}' lässt sich nicht aus '{ZIELE.get(ziel, ziel)}' berechnen")
    a = basis.annahmen.mit(**_kwargs(basis.annahmen, aenderungen))
    l = loese(a, ziel, zielwert, groesse)
    if l.wert is None:
        return aenderungen, l
    neu = normalisiere(basis.annahmen, {**aenderungen, groesse: l.wert})
    return neu, l


# --------------------------------------------------------------------------- Formular (Oberfläche)


def zahl_aus_text(text: str | None) -> float | None:
    if text is None or text.strip() == "":
        return None
    try:
        return float(text.strip().replace(" ", "").replace(",", "."))
    except ValueError:
        raise ObjektFehler(f"keine Zahl: {text!r}") from None


def eingabe_wert(p: Parameter, wert: Any) -> str:
    """Wert für das Eingabefeld (Prozente als Prozentzahl), so genau, dass ein unveränderter Wert unverändert zurückkommt."""
    if wert is None or p.art == "bool":
        return ""
    if p.art == "ek" and wert == "nebenkosten":
        return ""
    v = float(wert) * 100 if p.art == "pct" else float(wert)
    text = f"{v:.{6 if p.art == 'pct' else 2}f}".rstrip("0").rstrip(".")  # ohne Exponentialschreibweise
    return "0" if text in ("", "-0") else text


def aus_formular(basis: Annahmen, daten: dict[str, str]) -> dict[str, Any]:
    """Formularfelder `p_<name>` → geprüfte Änderungen. Prozente kommen als Prozentzahl (3,8 = 3,8 %).

    Die Miete kann als €/Jahr oder als €/m² und Monat geändert werden; welches Feld gilt, zeigt der Vergleich
    mit dem zuvor angezeigten Wert (`p_miete_m2_vorher`).
    """
    roh: dict[str, Any] = {}
    for p in PARAMETER:
        feld = f"p_{p.name}"
        if p.art == "bool":
            roh[p.name] = daten.get(feld) == "1"
            continue
        if p.art == "ek" and daten.get("p_eigenkapital_art") == "nebenkosten":
            roh[p.name] = "nebenkosten"
            continue
        try:
            v = zahl_aus_text(daten.get(feld))
        except ObjektFehler as exc:
            raise ObjektFehler(f"{p.label}: {exc}") from None
        if v is None:
            continue  # leeres Feld = Ausgangswert
        roh[p.name] = v / 100 if p.art == "pct" else v
    m2, vorher = zahl_aus_text(daten.get("p_miete_m2")), zahl_aus_text(daten.get("p_miete_m2_vorher"))
    flaeche = roh.get("wohnflaeche", basis.wohnflaeche)
    if m2 is not None and (vorher is None or abs(m2 - vorher) > 0.005) and flaeche:
        roh["miete_ist"] = m2 * 12 * flaeche
    return normalisiere(basis, roh)


def miete_m2(miete: float | None, flaeche: float | None) -> float | None:
    return None if not miete or not flaeche else round(miete / 12 / flaeche, 2)


# --------------------------------------------------------------------------- Szenarien


def _kennzahlen_json(k: dict[str, Any]) -> str:
    return json.dumps({n: k.get(n) for n in (*KENNZAHLEN, "kpe_status", "ausgeschlossen")}, ensure_ascii=False)


def _name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ObjektFehler("Bitte einen Namen für das Szenario angeben")
    if len(name) > MAX_NAME:
        raise ObjektFehler(f"Name zu lang (höchstens {MAX_NAME} Zeichen)")
    return name


def _als_dict(r: sqlite3.Row) -> dict[str, Any]:
    d = dict(r)
    d["annahmen"] = json.loads(d.pop("annahmen_json") or "{}")
    d["ergebnis"] = json.loads(d.pop("ergebnis_json") or "null")
    return d


def szenarien(conn: sqlite3.Connection, listing_id: int, profil_id: str | None = None) -> list[dict[str, Any]]:
    sql, args = "SELECT * FROM scenario WHERE listing_id = ?", [listing_id]
    if profil_id:
        sql, args = sql + " AND profile_id = ?", [*args, profil_id]
    return [_als_dict(r) for r in conn.execute(sql + " ORDER BY updated_at DESC, id DESC", args)]


def szenario(conn: sqlite3.Connection, szenario_id: int, listing_id: int | None = None) -> dict[str, Any]:
    r = conn.execute("SELECT * FROM scenario WHERE id = ?", (szenario_id,)).fetchone()
    if r is None or (listing_id is not None and r["listing_id"] != listing_id):
        raise ObjektFehler(f"Szenario {szenario_id} nicht gefunden")
    return _als_dict(r)


def speichere_szenario(conn: sqlite3.Connection, basis: Basis, name: str, aenderungen: dict[str, Any],
                       szenario_id: int | None = None) -> int:
    """Neues Szenario anlegen oder ein vorhandenes (gleiches Angebot und Profil) überschreiben."""
    name = _name(name)
    aenderungen = normalisiere(basis.annahmen, aenderungen)
    ergebnis = _kennzahlen_json(rechne(basis, aenderungen)["simulation"])
    ts = now_iso()
    lid, pid = basis.listing["id"], basis.profile.id
    if szenario_id is None:
        cur = conn.execute(
            "INSERT INTO scenario (listing_id, profile_id, name, annahmen_json, ergebnis_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lid, pid, name, json.dumps(aenderungen, ensure_ascii=False), ergebnis, ts, ts))
        conn.commit()
        return int(cur.lastrowid)  # type: ignore[arg-type]
    alt = szenario(conn, szenario_id, lid)
    if alt["profile_id"] != pid:
        raise ObjektFehler("Szenario gehört zu einem anderen Profil")
    conn.execute("UPDATE scenario SET name = ?, annahmen_json = ?, ergebnis_json = ?, updated_at = ? WHERE id = ?",
                 (name, json.dumps(aenderungen, ensure_ascii=False), ergebnis, ts, szenario_id))
    conn.commit()
    return szenario_id


def umbenennen(conn: sqlite3.Connection, szenario_id: int, listing_id: int, name: str) -> None:
    szenario(conn, szenario_id, listing_id)
    conn.execute("UPDATE scenario SET name = ?, updated_at = ? WHERE id = ?", (_name(name), now_iso(), szenario_id))
    conn.commit()


def loesche_szenario(conn: sqlite3.Connection, szenario_id: int, listing_id: int) -> None:
    szenario(conn, szenario_id, listing_id)
    conn.execute("DELETE FROM scenario WHERE id = ?", (szenario_id,))
    conn.commit()


def abweichungen(gespeichert: dict[str, Any] | None, aktuell: dict[str, Any]) -> list[str]:
    """Kennzahlen, die sich seit dem Speichern geändert haben (neue Extraktion, andere Profil-Annahmen)."""
    if not gespeichert:
        return []
    out = []
    for n, (label, art) in KENNZAHLEN.items():
        if n not in gespeichert:  # Kennzahl gab es beim Speichern noch nicht
            continue
        a, b = gespeichert.get(n), aktuell.get(n)
        if (a is None) != (b is None) or (a is not None and not math.isclose(a, b, rel_tol=1e-6, abs_tol=0.5 if art == "eur" else 1e-6)):
            out.append(label)
    return out


def vergleich(basis: Basis, auswahl: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Spalten für den Vergleich: Ausgangswert, dann bis zu drei Szenarien (mit aktuellen Ausgangswerten gerechnet)."""
    if not 1 <= len(auswahl) <= MAX_VERGLEICH:
        raise ObjektFehler(f"1 bis {MAX_VERGLEICH} Szenarien zum Vergleich auswählen")
    spalten = [{"name": "Ausgangswert", "id": None, "aenderungen": {}, "werte": rechne(basis, {})["basis"]}]
    for s in auswahl:
        ae = normalisiere(basis.annahmen, s["annahmen"])
        r = rechne(basis, ae)
        spalten.append({"name": s["name"], "id": s["id"], "aenderungen": ae, "annahmen": r["annahmen"], "werte": r["simulation"],
                        "abweichungen": abweichungen(s["ergebnis"], r["simulation"])})
    spalten[0]["annahmen"] = basis.annahmen
    return spalten
