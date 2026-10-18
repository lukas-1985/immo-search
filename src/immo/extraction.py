"""Merkmale aus dem Freitext: Schema, Prüfungen und Speichern.

Quellen und Rang (höhere Stufen werden nie von niedrigeren überschrieben):
    portal > regel > claude > schätzung

Prüfungen beim Speichern (deterministisch, für Regel- und Claude-Werte gleich):
    1. JSON-Schema der Objektart
    2. Belegstelle steht wörtlich in Titel oder Beschreibung
    3. Plausibilität (z. B. Miete/Kaufpreis zwischen 1 % und 25 %)
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .config import PROJECT_ROOT
from .db import now_iso

SCHEMA_DIR = PROJECT_ROOT / ".claude" / "skills" / "immo-analyse" / "extraction_schema"
SOURCE_RANK = {"schätzung": 0, "claude": 1, "regel": 2, "portal": 3}
MAX_VERSUCHE = 3  # danach legt `pending` das Angebot nicht mehr vor (bis sich der Text ändert)


@dataclass(frozen=True)
class ExtractionSchema:
    objektart: str
    version: int
    raw: dict
    validator: Draft202012Validator

    @property
    def fields(self) -> list[str]:
        return list(self.raw["properties"]["felder"]["properties"])


@cache
def load_schema(objektart: str, schema_dir: Path = SCHEMA_DIR) -> ExtractionSchema:
    path = schema_dir / f"{objektart}.json"
    if not path.exists():
        raise FileNotFoundError(f"Kein Extraktionsschema für Objektart '{objektart}' ({path})")
    raw = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(raw)
    return ExtractionSchema(objektart, int(raw["x-schema-version"]), raw, Draft202012Validator(raw))


def schema_errors(schema: ExtractionSchema, result: Any) -> list[str]:
    errors = sorted(schema.validator.iter_errors(result), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '(Wurzel)'}: {e.message}" for e in errors]


# --------------------------------------------------------------------------- Belegstelle

_WS = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"\s*(?:…|\.\.\.)\s*")
_QUOTES = str.maketrans({"„": '"', "“": '"', "”": '"', "‚": "'", "‘": "'", "’": "'", "–": "-", "—": "-", " ": " "})


def _norm(text: str) -> str:
    return _WS.sub(" ", text.translate(_QUOTES)).strip().casefold()


def belegstelle_found(beleg: str, *texts: str | None) -> bool:
    """Jeder durch '…' getrennte Teil der Belegstelle muss wörtlich (bis auf Leerraum/Anführungszeichen) vorkommen."""
    haystack = _norm(" \n ".join(t for t in texts if t))
    parts = [_norm(p) for p in _ELLIPSIS.split(beleg) if p.strip()]
    return bool(parts) and all(p in haystack for p in parts)


# --------------------------------------------------------------------------- Plausibilität


def plausibility_error(feld: str, wert: Any, felder: dict[str, Any], preis: float | None) -> str | None:
    if feld in ("jahresnettokaltmiete_ist", "jahresnettokaltmiete_soll") and preis:
        quote = wert / preis
        if quote < 0.01:
            return f"Miete {wert:,.0f} € entspricht {quote:.2%} des Kaufpreises – Monats- statt Jahreswert?"
        if quote > 0.25:
            return f"Miete {wert:,.0f} € entspricht {quote:.2%} des Kaufpreises – unplausibel hoch"
    if feld == "leerstand_einheiten":
        we = felder.get("wohneinheiten", {}).get("wert")
        ge = felder.get("gewerbeeinheiten", {}).get("wert") or 0
        if we is not None and wert > we + ge:
            return f"Leerstand ({wert}) größer als Einheiten ({we + ge})"
    return None


# --------------------------------------------------------------------------- Speichern


@dataclass
class FieldReport:
    gespeichert: list[str] = field(default_factory=list)
    uebersprungen: dict[str, str] = field(default_factory=dict)  # feld → Grund
    abgelehnt: dict[str, str] = field(default_factory=dict)  # feld → Grund


def existing_sources(conn: sqlite3.Connection, listing_id: int) -> dict[str, str]:
    return {r["feld"]: r["quelle"] for r in conn.execute("SELECT feld, quelle FROM extraction WHERE listing_id = ?", (listing_id,))}


def store_fields(
    conn: sqlite3.Connection,
    listing: sqlite3.Row,
    felder: dict[str, dict[str, Any]],
    quelle: str,
    schema_version: int,
) -> FieldReport:
    """Ersetzt alle Werte der Quelle `quelle` für dieses Angebot durch `felder` (nach Prüfung 2 und 3).

    Felder einer höherrangigen Quelle bleiben unangetastet.
    """
    report = FieldReport()
    rank = SOURCE_RANK[quelle]
    conn.execute("DELETE FROM extraction WHERE listing_id = ? AND quelle = ?", (listing["id"], quelle))
    existing = existing_sources(conn, listing["id"])
    ts = now_iso()
    for feld, item in felder.items():
        if not belegstelle_found(item["belegstelle"], listing["titel"], listing["beschreibung"]):
            report.abgelehnt[feld] = "Belegstelle nicht im Text gefunden"
            continue
        if err := plausibility_error(feld, item["wert"], felder, listing["preis"]):
            report.abgelehnt[feld] = err
            continue
        other = existing.get(feld)
        if other is not None and SOURCE_RANK[other] > rank:
            report.uebersprungen[feld] = f"bereits aus Quelle '{other}'"
            continue
        conn.execute(
            """INSERT INTO extraction (listing_id, feld, wert, quelle, konfidenz, belegstelle, schema_version, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (listing_id, feld) DO UPDATE SET wert = excluded.wert, quelle = excluded.quelle,
                   konfidenz = excluded.konfidenz, belegstelle = excluded.belegstelle,
                   schema_version = excluded.schema_version, extracted_at = excluded.extracted_at""",
            (listing["id"], feld, json.dumps(_with_rechenweg(item), ensure_ascii=False), quelle,
             item.get("konfidenz"), item["belegstelle"], schema_version, ts),
        )
        report.gespeichert.append(feld)
    return report


def _with_rechenweg(item: dict[str, Any]) -> Any:
    """`wert` als JSON; ein Rechenweg wird mitgespeichert, damit er in Detailansicht und Digest sichtbar ist."""
    if item.get("rechenweg"):
        return {"wert": item["wert"], "rechenweg": item["rechenweg"]}
    return item["wert"]


def field_values(conn: sqlite3.Connection, listing_id: int) -> dict[str, dict[str, Any]]:
    """Alle gespeicherten Merkmale eines Angebots: feld → {wert, quelle, konfidenz, belegstelle[, rechenweg]}."""
    out = {}
    for r in conn.execute("SELECT * FROM extraction WHERE listing_id = ?", (listing_id,)):
        raw = json.loads(r["wert"])
        entry = {"quelle": r["quelle"], "konfidenz": r["konfidenz"], "belegstelle": r["belegstelle"]}
        if isinstance(raw, dict) and set(raw) == {"wert", "rechenweg"}:
            entry.update(raw)
        else:
            entry["wert"] = raw
        out[r["feld"]] = entry
    return out
