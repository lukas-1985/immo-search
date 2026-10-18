"""Schnittstelle zu Claude: `pending` legt Angebote vor, `save` prüft und speichert die Antwort.

Claude wertet jedes Angebot nur einmal aus. Erneut vorgelegt wird es nur, wenn
- sich die Beschreibung geändert hat (Hash-Vergleich),
- das Extraktionsschema eine neue Version hat,
- der letzte Versuch abgelehnt wurde (höchstens MAX_VERSUCHE Mal) oder
- die Neuauswertung ausdrücklich angefordert wird (`reextract`).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .db import now_iso
from .extraction import MAX_VERSUCHE, SOURCE_RANK, existing_sources, load_schema, schema_errors, store_fields

MAX_TEXT = 8000  # Zeichen Beschreibung je Angebot (Kontingent schonen)
MIN_TEXT = 40  # kürzere Beschreibungen lohnen keine Auswertung


def objektart_by_listing(conn: sqlite3.Connection, config: Config, only_profile: str | None = None) -> dict[int, str]:
    """Aktive Angebote der (aktiven) Profile mit der Objektart ihres ersten Profils."""
    profiles = {p.id: p.objektart for p in config.active_profiles(only_profile)}
    if not profiles:
        return {}
    marks = ",".join("?" * len(profiles))
    rows = conn.execute(
        f"""SELECT lp.listing_id, lp.profile_id FROM listing_profile lp JOIN listing l ON l.id = lp.listing_id
            WHERE l.status_portal = 'aktiv' AND lp.profile_id IN ({marks}) ORDER BY lp.listing_id, lp.profile_id""",
        tuple(profiles),
    ).fetchall()
    out: dict[int, str] = {}
    for r in rows:
        out.setdefault(r["listing_id"], profiles[r["profile_id"]])
    return out


def _needs_extraction(status: sqlite3.Row | None, beschreibung_hash: str | None, schema_version: int) -> bool:
    if status is None:
        return True
    if status["beschreibung_hash"] != beschreibung_hash or status["schema_version"] != schema_version:
        return True
    return status["status"] == "fehler" and status["versuche"] < MAX_VERSUCHE


def pending(
    conn: sqlite3.Connection,
    config: Config,
    limit: int = 20,
    only_profile: str | None = None,
    listing_id: int | None = None,
    reextract: bool = False,
) -> dict[str, Any]:
    """Kompakte Vorlage für Claude: nur relevante Felder, bekannte Merkmale und gesuchte Felder."""
    if listing_id is not None:
        candidates = {k: v for k, v in objektart_by_listing(conn, config).items() if k == listing_id}
    else:
        candidates = objektart_by_listing(conn, config, only_profile)

    items, offen = [], 0
    for lid, objektart in candidates.items():
        schema = load_schema(objektart)
        l = conn.execute("SELECT * FROM listing WHERE id = ?", (lid,)).fetchone()
        if not l["beschreibung"] or len(l["beschreibung"]) < MIN_TEXT:
            continue
        status = conn.execute("SELECT * FROM extraction_status WHERE listing_id = ?", (lid,)).fetchone()
        if not (reextract and listing_id is not None) and not _needs_extraction(status, l["beschreibung_hash"], schema.version):
            continue
        offen += 1
        if len(items) >= limit:
            continue
        sources = existing_sources(conn, lid)
        # Felder aus höherrangigen Quellen braucht Claude nicht erneut zu suchen
        bekannt = {
            r["feld"]: json.loads(r["wert"])
            for r in conn.execute("SELECT feld, wert, quelle FROM extraction WHERE listing_id = ?", (lid,))
            if SOURCE_RANK[r["quelle"]] > SOURCE_RANK["claude"]
        }
        items.append({
            "listing_id": lid,
            "objektart": objektart,
            "schema_version": schema.version,
            "beschreibung_hash": l["beschreibung_hash"],
            "titel": l["titel"],
            "ort": " ".join(x for x in (l["plz"], l["ort"]) if x) or None,
            "preis": l["preis"],
            "wohnflaeche": l["flaeche"],
            "baujahr": l["baujahr"],
            "bekannt": bekannt,
            "gesucht": [f for f in schema.fields if sources.get(f) not in ("regel", "portal")],
            "versuch": (status["versuche"] + 1) if status and status["status"] == "fehler" else 1,
            "letzter_fehler": status["letzter_fehler"] if status and status["status"] == "fehler" else None,
            "text": l["beschreibung"][:MAX_TEXT],
        })
    return {"anzahl": len(items), "offen_gesamt": offen, "angebote": items}


@dataclass
class SaveReport:
    angenommen: dict[int, dict[str, Any]] = field(default_factory=dict)
    abgelehnt: dict[int, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"angenommen": self.angenommen, "abgelehnt": self.abgelehnt}


def _set_status(conn: sqlite3.Connection, listing_id: int, beschreibung_hash: str | None, version: int, ok: bool, fehler: str | None) -> None:
    conn.execute(
        """INSERT INTO extraction_status (listing_id, beschreibung_hash, schema_version, status, versuche, letzter_fehler, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (listing_id) DO UPDATE SET
               versuche = CASE WHEN excluded.status = 'ok' THEN 0
                               WHEN extraction_status.beschreibung_hash IS NOT excluded.beschreibung_hash THEN 1
                               ELSE extraction_status.versuche + 1 END,
               beschreibung_hash = excluded.beschreibung_hash, schema_version = excluded.schema_version,
               status = excluded.status, letzter_fehler = excluded.letzter_fehler, updated_at = excluded.updated_at""",
        (listing_id, beschreibung_hash, version, "ok" if ok else "fehler", 0 if ok else 1, fehler, now_iso()),
    )


def save(conn: sqlite3.Connection, config: Config, payload: Any) -> SaveReport:
    """Claude-Ergebnisse prüfen und speichern. Ungültige Ergebnisse werden abgelehnt und später erneut vorgelegt."""
    report = SaveReport()
    results = payload.get("ergebnisse") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("Erwartet: {\"ergebnisse\": [ … ]}")

    objektarten = objektart_by_listing(conn, config)
    for result in results:
        lid = result.get("listing_id") if isinstance(result, dict) else None
        if not isinstance(lid, int) or lid not in objektarten:
            report.abgelehnt[lid if isinstance(lid, int) else -1] = ["unbekanntes oder nicht aktives Angebot"]
            continue
        schema = load_schema(objektarten[lid])
        listing = conn.execute("SELECT * FROM listing WHERE id = ?", (lid,)).fetchone()

        errors = schema_errors(schema, result)
        if not errors and result["beschreibung_hash"] != listing["beschreibung_hash"]:
            errors = ["Beschreibung hat sich seit der Vorlage geändert – Angebot wird neu vorgelegt"]
        if errors:
            report.abgelehnt[lid] = errors
            _set_status(conn, lid, listing["beschreibung_hash"], schema.version, False, "; ".join(errors)[:1000])
            continue

        fields = store_fields(conn, listing, result["felder"], "claude", schema.version)
        report.angenommen[lid] = {
            "gespeichert": fields.gespeichert,
            "uebersprungen": fields.uebersprungen,
            "feld_abgelehnt": fields.abgelehnt,
        }
        _set_status(conn, lid, listing["beschreibung_hash"], schema.version, True,
                    "; ".join(f"{k}: {v}" for k, v in fields.abgelehnt.items()) or None)
    conn.commit()
    return report
