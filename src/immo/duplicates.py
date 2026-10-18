"""Duplikate über Portale: dasselbe Objekt auf IS24, Immowelt und Kleinanzeigen bekommt eine `duplicate_group`.

Fredy liefert keine Duplikat-Kennung (offener Punkt 5). Erkannt wird nur, was eindeutig ist:
verschiedene Portale, gleiche PLZ, fast gleicher Titel, Preis ± 5 %, Fläche ± 2 % (wenn beide bekannt).
Lieber ein Duplikat übersehen als zwei verschiedene Häuser zusammenlegen.

Die Gruppen-ID ist die kleinste Listing-ID der Gruppe; sie bleibt stabil, solange die Gruppe besteht.
Der Workflow-Status hängt an der Gruppe.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
from itertools import combinations

TITEL_AEHNLICHKEIT = 0.9
PREIS_TOLERANZ = 0.05
FLAECHE_TOLERANZ = 0.02


def _norm(titel: str | None) -> str:
    return re.sub(r"[^0-9a-zäöüß]+", " ", (titel or "").casefold()).strip()


def _nah(a: float | None, b: float | None, toleranz: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= toleranz * max(a, b)


def ist_duplikat(a: sqlite3.Row | dict, b: sqlite3.Row | dict) -> bool:
    if a["provider"] == b["provider"] or not a["plz"] or a["plz"] != b["plz"]:
        return False
    if not _nah(a["preis"], b["preis"], PREIS_TOLERANZ):
        return False
    if a["flaeche"] and b["flaeche"] and not _nah(a["flaeche"], b["flaeche"], FLAECHE_TOLERANZ):
        return False
    ta, tb = _norm(a["titel"]), _norm(b["titel"])
    return bool(ta) and difflib.SequenceMatcher(None, ta, tb).ratio() >= TITEL_AEHNLICHKEIT


def _workflow_uebertragen(conn: sqlite3.Connection, alte: int, neue: int) -> None:
    """Status einer aufgelösten Gruppe in die neue übernehmen; bei zwei Status gilt der neuere."""
    a = conn.execute("SELECT * FROM workflow WHERE duplicate_group = ?", (alte,)).fetchone()
    if a is not None:
        n = conn.execute("SELECT updated_at FROM workflow WHERE duplicate_group = ?", (neue,)).fetchone()
        if n is None or a["updated_at"] > n["updated_at"]:
            conn.execute("DELETE FROM workflow WHERE duplicate_group = ?", (neue,))
            conn.execute("UPDATE workflow SET duplicate_group = ? WHERE duplicate_group = ?", (neue, alte))
        else:
            conn.execute("DELETE FROM workflow WHERE duplicate_group = ?", (alte,))
    conn.execute("UPDATE workflow_history SET duplicate_group = ? WHERE duplicate_group = ?", (neue, alte))


def gruppiere_duplikate(conn: sqlite3.Connection) -> int:
    """Setzt `duplicate_group` für alle Angebote neu. Gibt die Zahl der Angebote in Mehrfachgruppen zurück."""
    rows = conn.execute("SELECT id, provider, plz, titel, preis, flaeche FROM listing ORDER BY id").fetchall()
    eltern = {r["id"]: r["id"] for r in rows}

    def wurzel(i: int) -> int:
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    nach_plz: dict[str, list] = {}
    for r in rows:
        if r["plz"]:
            nach_plz.setdefault(r["plz"], []).append(r)
    for gruppe in nach_plz.values():
        for a, b in combinations(gruppe, 2):
            if ist_duplikat(a, b):
                wa, wb = wurzel(a["id"]), wurzel(b["id"])
                eltern[max(wa, wb)] = min(wa, wb)  # kleinste ID gewinnt

    gruppen = {i: wurzel(i) for i in eltern}
    alt = {r["id"]: r["duplicate_group"] for r in conn.execute("SELECT id, duplicate_group FROM listing")}
    conn.executemany("UPDATE listing SET duplicate_group = ? WHERE id = ? AND duplicate_group IS NOT ?",
                     [(g, i, g) for i, g in gruppen.items()])
    verbleibend = set(gruppen.values())
    for alte, neue in {(alt[i], g) for i, g in gruppen.items() if alt[i] is not None and alt[i] != g}:
        if alte not in verbleibend:
            _workflow_uebertragen(conn, alte, neue)
    conn.commit()
    groesse: dict[int, int] = {}
    for g in gruppen.values():
        groesse[g] = groesse.get(g, 0) + 1
    return sum(n for n in groesse.values() if n > 1)
