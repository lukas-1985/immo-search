"""Status-Workflow und Notizen. Der Status hängt an der Duplikatgruppe; jede Änderung landet im Verlauf."""

from __future__ import annotations

import sqlite3
from typing import Literal

from .config import Config
from .db import now_iso

Quelle = Literal["ui", "mcp", "system"]


class WorkflowFehler(ValueError):
    pass


def _gruppe(conn: sqlite3.Connection, listing_id: int) -> int:
    row = conn.execute("SELECT id, duplicate_group FROM listing WHERE id = ?", (listing_id,)).fetchone()
    if row is None:
        raise WorkflowFehler(f"Angebot {listing_id} nicht gefunden")
    return row["duplicate_group"] or row["id"]


def erlaubte_status(config: Config) -> list[str]:
    return config.settings.workflow.status + config.settings.workflow.end_status


def setze_status(conn: sqlite3.Connection, config: Config, listing_id: int, status: str, quelle: Quelle,
                 notiz: str | None = None) -> dict:
    if status not in erlaubte_status(config):
        raise WorkflowFehler(f"Unbekannter Status '{status}' (erlaubt: {', '.join(erlaubte_status(config))})")
    gruppe = _gruppe(conn, listing_id)
    alt = conn.execute("SELECT status FROM workflow WHERE duplicate_group = ?", (gruppe,)).fetchone()
    alt_status = alt["status"] if alt else None
    ts = now_iso()
    conn.execute(
        """INSERT INTO workflow (duplicate_group, status, updated_at, updated_by) VALUES (?, ?, ?, ?)
           ON CONFLICT (duplicate_group) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at,
               updated_by = excluded.updated_by""",
        (gruppe, status, ts, quelle),
    )
    conn.execute(
        "INSERT INTO workflow_history (duplicate_group, status_alt, status_neu, quelle, notiz, zeitpunkt) VALUES (?, ?, ?, ?, ?, ?)",
        (gruppe, alt_status, status, quelle, (notiz or "").strip() or None, ts),
    )
    conn.commit()
    return {"listing_id": listing_id, "gruppe": gruppe, "status_alt": alt_status or "neu", "status": status}


def notiz_hinzufuegen(conn: sqlite3.Connection, listing_id: int, text: str, quelle: Quelle) -> dict:
    text = (text or "").strip()
    if not text:
        raise WorkflowFehler("Notiz ist leer")
    if len(text) > 5000:
        raise WorkflowFehler("Notiz ist zu lang (max. 5000 Zeichen)")
    _gruppe(conn, listing_id)
    cur = conn.execute("INSERT INTO note (listing_id, text, quelle, created_at) VALUES (?, ?, ?, ?)",
                       (listing_id, text, quelle, now_iso()))
    conn.commit()
    return {"id": cur.lastrowid, "listing_id": listing_id}
