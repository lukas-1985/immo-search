"""Lesende Abfragen für Oberfläche und MCP (eine Logik, zwei Zugänge).

Alles kommt aus `data/immo.db`; Score und Rechenweg stammen aus der letzten Bewertung (`score.kpis_json`).
Je Duplikatgruppe erscheint ein Angebot (das am besten bewertete), die anderen Portale stehen unter `portale`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import Config
from .extraction import field_values

SORTIERUNGEN = ("score", "preis", "preisabstand", "bruttorendite", "standzeit", "neu", "einheiten")


def _tage_seit(iso: str | None) -> int | None:
    if not iso:
        return None
    return (datetime.now(UTC) - datetime.fromisoformat(iso)).days


def standard_profil(config: Config, profil: str | None = None) -> str | None:
    if profil and profil in config.profiles:
        return profil
    aktive = config.active_profiles()
    return aktive[0].id if aktive else None


def _portale(conn: sqlite3.Connection) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for r in conn.execute("SELECT id, provider, url, duplicate_group, status_portal FROM listing ORDER BY id"):
        g = r["duplicate_group"] or r["id"]
        out.setdefault(g, []).append({"listing_id": r["id"], "portal": r["provider"], "url": r["url"], "aktiv": r["status_portal"] == "aktiv"})
    return out


def _preisaenderung(conn: sqlite3.Connection) -> dict[int, float]:
    """Relative Änderung erster → letzter Preis je Angebot (nur wenn es eine gab)."""
    out = {}
    for r in conn.execute(
        """SELECT listing_id,
                  (SELECT preis FROM price_history p2 WHERE p2.listing_id = p.listing_id ORDER BY datum, rowid LIMIT 1) AS erster,
                  (SELECT preis FROM price_history p3 WHERE p3.listing_id = p.listing_id ORDER BY datum DESC, rowid DESC LIMIT 1) AS letzter
           FROM price_history p GROUP BY listing_id HAVING COUNT(*) > 1"""
    ):
        if r["erster"]:
            out[r["listing_id"]] = (r["letzter"] - r["erster"]) / r["erster"]
    return out


def _einheiten(conn: sqlite3.Connection) -> dict[int, int]:
    return {r["listing_id"]: json.loads(r["wert"]) for r in conn.execute("SELECT listing_id, wert FROM extraction WHERE feld = 'wohneinheiten'")}


def liste(
    conn: sqlite3.Connection,
    config: Config,
    *,
    profil: str | None = None,
    status: str | None = None,
    score_min: float | None = None,
    score_max: float | None = None,
    rendite_min: float | None = None,
    preis_max: float | None = None,
    preisabstand_max: float | None = None,
    ort: str | None = None,
    portal: str | None = None,
    nur_unvollstaendig: bool = False,
    ausgeschlossene: bool = False,
    entfernte: bool = False,
    q: str | None = None,
    seit: str | None = None,
    sortierung: str = "score",
    absteigend: bool = True,
    seite: int = 1,
    pro_seite: int = 50,
) -> dict[str, Any]:
    profil = standard_profil(config, profil)
    if profil is None:
        return {"profil": None, "items": [], "gesamt": 0, "seite": 1, "seiten": 1}
    end = config.settings.workflow.end_status
    sql = """SELECT l.*, s.score, s.kaufpreisempfehlung, s.preisabstand, s.hard_filter_result, s.ausschlussgrund,
                    s.kpis_json, w.status AS wf_status
             FROM listing l JOIN listing_profile lp ON lp.listing_id = l.id AND lp.profile_id = ?
             LEFT JOIN score s ON s.listing_id = l.id AND s.profile_id = lp.profile_id
             LEFT JOIN workflow w ON w.duplicate_group = l.duplicate_group
             WHERE 1 = 1"""
    params: list[Any] = [profil]
    if not entfernte:
        sql += " AND l.status_portal = 'aktiv'"
    if not ausgeschlossene:
        sql += " AND (s.hard_filter_result IS NULL OR s.hard_filter_result = 'bestanden')"
    if status:
        if status == "neu":
            sql += " AND (w.status IS NULL OR w.status = 'neu')"
        else:
            sql += " AND w.status = ?"
            params.append(status)
    elif end:
        sql += f" AND (w.status IS NULL OR w.status NOT IN ({','.join('?' * len(end))}))"
        params += end
    if ort:
        sql += " AND (l.ort LIKE ? OR l.plz LIKE ? OR l.adresse LIKE ?)"
        params += [f"%{ort}%"] * 3
    if portal:
        sql += " AND l.provider = ?"
        params.append(portal)
    if q:
        sql += " AND (l.titel LIKE ? OR l.beschreibung LIKE ?)"
        params += [f"%{q}%"] * 2
    if seit:
        sql += " AND l.first_seen >= ?"
        params.append(seit)
    sql += " ORDER BY s.score IS NULL, s.score DESC, l.id"

    portale = _portale(conn)
    preisaenderung = _preisaenderung(conn)
    einheiten = _einheiten(conn)
    gesehen: set[int] = set()
    items: list[dict[str, Any]] = []
    for r in conn.execute(sql, params):
        gruppe = r["duplicate_group"] or r["id"]
        if gruppe in gesehen:
            continue
        gesehen.add(gruppe)
        details = json.loads(r["kpis_json"]) if r["kpis_json"] else {}
        alle = details.get("alle_kpis", {})
        rendite = (alle.get("bruttorendite") or {}).get("wert")
        unvollst = details.get("unvollstaendig", [])
        item = {
            "id": r["id"], "titel": r["titel"], "ort": r["ort"], "plz": r["plz"], "preis": r["preis"],
            "flaeche": r["flaeche"], "score": r["score"], "bruttorendite": rendite,
            "rendite_qualitaet": (alle.get("bruttorendite") or {}).get("qualitaet"),
            "kaufpreisempfehlung": r["kaufpreisempfehlung"], "preisabstand": r["preisabstand"],
            "einheiten": einheiten.get(r["id"]), "portale": portale.get(gruppe, []),
            "standzeit_tage": _tage_seit(r["first_seen"]), "first_seen": r["first_seen"],
            "preisaenderung": preisaenderung.get(r["id"]), "status": r["wf_status"] or "neu",
            "unvollstaendig": unvollst, "ausgeschlossen": r["hard_filter_result"] == "ausgeschlossen",
            "ausschlussgrund": r["ausschlussgrund"], "status_portal": r["status_portal"],
        }
        if score_min is not None and (item["score"] is None or item["score"] < score_min):
            continue
        if score_max is not None and (item["score"] is None or item["score"] > score_max):
            continue
        if rendite_min is not None and (rendite is None or rendite < rendite_min):
            continue
        if preis_max is not None and (item["preis"] is None or item["preis"] > preis_max):
            continue
        if preisabstand_max is not None and (item["preisabstand"] is None or item["preisabstand"] > preisabstand_max):
            continue
        if nur_unvollstaendig and not unvollst:
            continue
        items.append(item)

    schluessel = {
        "score": lambda i: i["score"], "preis": lambda i: i["preis"], "preisabstand": lambda i: i["preisabstand"],
        "bruttorendite": lambda i: i["bruttorendite"], "standzeit": lambda i: i["standzeit_tage"],
        "neu": lambda i: i["first_seen"], "einheiten": lambda i: i["einheiten"],
    }[sortierung if sortierung in SORTIERUNGEN else "score"]
    vorhanden = [i for i in items if schluessel(i) is not None]
    fehlend = [i for i in items if schluessel(i) is None]
    items = sorted(vorhanden, key=schluessel, reverse=absteigend) + fehlend

    gesamt = len(items)
    pro_seite = max(1, min(pro_seite, 500))
    seiten = max(1, -(-gesamt // pro_seite))
    seite = max(1, min(seite, seiten))
    return {"profil": profil, "items": items[(seite - 1) * pro_seite : seite * pro_seite],
            "gesamt": gesamt, "seite": seite, "seiten": seiten}


def detail(conn: sqlite3.Connection, config: Config, listing_id: int) -> dict[str, Any] | None:
    l = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
    if l is None:
        return None
    gruppe = l["duplicate_group"] or l["id"]
    bewertungen = {}
    for s in conn.execute("SELECT * FROM score WHERE listing_id = ?", (listing_id,)):
        bewertungen[s["profile_id"]] = {
            "score": s["score"], "kaufpreisempfehlung": s["kaufpreisempfehlung"], "preisabstand": s["preisabstand"],
            "ausgeschlossen": s["hard_filter_result"] == "ausgeschlossen", "ausschlussgrund": s["ausschlussgrund"],
            "details": json.loads(s["kpis_json"]) if s["kpis_json"] else {}, "bewertet_am": s["scored_at"],
        }
    wf = conn.execute("SELECT * FROM workflow WHERE duplicate_group = ?", (gruppe,)).fetchone()
    return {
        "listing": {k: l[k] for k in l.keys() if k not in ("bilder", "beschreibung")},
        "beschreibung": l["beschreibung"],
        "bilder": json.loads(l["bilder"]) if l["bilder"] else [],
        "profile": [r["profile_id"] for r in conn.execute("SELECT profile_id FROM listing_profile WHERE listing_id = ?", (listing_id,))],
        "portale": _portale(conn).get(gruppe, []),
        "merkmale": field_values(conn, listing_id),
        "bewertungen": bewertungen,
        "preisverlauf": [dict(r) for r in conn.execute("SELECT datum, preis FROM price_history WHERE listing_id = ? ORDER BY datum, rowid", (listing_id,))],
        "standzeit_tage": _tage_seit(l["first_seen"]),
        "status": wf["status"] if wf else "neu",
        "status_verlauf": [dict(r) for r in conn.execute(
            "SELECT status_alt, status_neu, quelle, notiz, zeitpunkt FROM workflow_history WHERE duplicate_group = ? ORDER BY id DESC", (gruppe,))],
        "notizen": [dict(r) for r in conn.execute(
            """SELECT n.id, n.listing_id, n.text, n.quelle, n.created_at FROM note n JOIN listing l2 ON l2.id = n.listing_id
               WHERE COALESCE(l2.duplicate_group, l2.id) = ? ORDER BY n.id DESC""", (gruppe,))],
        "extraktion": dict(r) if (r := conn.execute("SELECT * FROM extraction_status WHERE listing_id = ?", (listing_id,)).fetchone()) else None,
    }


def uebersicht(conn: sqlite3.Connection, config: Config) -> dict[str, Any]:
    jetzt = datetime.now(UTC)
    heute = jetzt.replace(hour=0, minute=0, second=0).isoformat()
    woche = (jetzt - timedelta(days=7)).isoformat()
    neu = lambda seit: conn.execute("SELECT COUNT(*) FROM listing WHERE first_seen >= ?", (seit,)).fetchone()[0]  # noqa: E731
    preissenkungen = conn.execute(
        """SELECT COUNT(DISTINCT p.listing_id) FROM price_history p
           WHERE p.datum >= ? AND p.preis < (SELECT p2.preis FROM price_history p2 WHERE p2.listing_id = p.listing_id
                                              AND p2.datum < p.datum ORDER BY p2.datum DESC LIMIT 1)""", (woche,)).fetchone()[0]
    status = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) AS n FROM workflow GROUP BY status")}
    portale = [dict(r) for r in conn.execute(
        """SELECT provider AS portal, COUNT(*) AS angebote, SUM(status_portal = 'aktiv') AS aktiv, MAX(first_seen) AS letztes_neues
           FROM listing GROUP BY provider ORDER BY provider""")]
    for p in portale:
        p["tage_seit_neuem"] = _tage_seit(p["letztes_neues"])
    laeufe = [dict(r) for r in conn.execute("SELECT schritt, profile_id, start, ende, fehler FROM run_log ORDER BY id DESC LIMIT 8")]
    top = {p.id: liste(conn, config, profil=p.id, pro_seite=10)["items"] for p in config.active_profiles()}
    return {
        "neu_heute": neu(heute), "neu_woche": neu(woche), "preissenkungen_woche": preissenkungen,
        "aktiv": conn.execute("SELECT COUNT(*) FROM listing WHERE status_portal = 'aktiv'").fetchone()[0],
        "status": status, "portale": portale, "laeufe": laeufe, "top": top,
        "top_score": max((i["score"] for items in top.values() for i in items if i["score"] is not None), default=None),
    }


def aenderungen(conn: sqlite3.Connection, seit: str) -> dict[str, Any]:
    """Neu, Preisänderungen und entfernt seit Zeitpunkt (ISO)."""
    neu = [dict(r) for r in conn.execute("SELECT id, titel, ort, preis, provider, first_seen FROM listing WHERE first_seen >= ? ORDER BY first_seen DESC", (seit,))]
    preise = [dict(r) for r in conn.execute(
        """SELECT l.id, l.titel, p.datum, p.preis,
                  (SELECT p2.preis FROM price_history p2 WHERE p2.listing_id = p.listing_id AND p2.datum < p.datum ORDER BY p2.datum DESC LIMIT 1) AS vorher
           FROM price_history p JOIN listing l ON l.id = p.listing_id WHERE p.datum >= ? ORDER BY p.datum DESC""", (seit,))
        if r["vorher"] is not None]
    entfernt = [dict(r) for r in conn.execute("SELECT id, titel, ort, preis, provider, last_seen FROM listing WHERE status_portal = 'entfernt' AND last_seen >= ?", (seit,))]
    return {"seit": seit, "neu": neu, "preisaenderungen": preise, "entfernt": entfernt}


def statistik(conn: sqlite3.Connection, config: Config) -> dict[str, Any]:
    out: dict[str, Any] = {"portale": uebersicht(conn, config)["portale"]}
    for p in config.active_profiles():
        rows = conn.execute("SELECT score, hard_filter_result, ausschlussgrund FROM score WHERE profile_id = ?", (p.id,)).fetchall()
        scores = sorted(r["score"] for r in rows if r["score"] is not None and r["hard_filter_result"] == "bestanden")
        gruende: dict[str, int] = {}
        for r in rows:
            if r["ausschlussgrund"]:
                k = r["ausschlussgrund"].split(" ")[0]
                gruende[k] = gruende.get(k, 0) + 1
        out[p.id] = {
            "bewertet": len(rows), "bestanden": len(scores), "ausschlussgruende": gruende,
            "score_median": scores[len(scores) // 2] if scores else None,
            "score_verteilung": {f"{b}-{b + 20}": sum(b <= s < b + 20 or (b == 80 and s == 100) for s in scores) for b in range(0, 100, 20)},
        }
    return out
