"""Überwachung: Läuft das System noch? Ergebnis in `run_log` (Schritt `health`).

Prüfungen (Grenzwerte aus settings.yaml → health):
- `portal:<id>`  Jedes Portal hat innerhalb von `max_tage_ohne_angebot` Tagen mindestens 1 neues Angebot
                 geliefert (`listing.first_seen`). Bleibt ein Portal stumm, ist meist der Bot-Schutz schuld.
- `sync`         Der letzte fehlerfreie Sync ist höchstens `max_stunden_ohne_sync` Stunden alt.
- `backup`       Das letzte fehlerfreie Backup ist höchstens `max_stunden_ohne_backup` Stunden alt.
- `server`       `GET /health` des immo-servers antwortet mit `ok`.

Bis Phase 5 wird nur protokolliert; der Telegram-Alarm hängt sich später an `probleme` an.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from .config import Config
from .db import now_iso

ServerAbfrage = Callable[[str, float], tuple[bool, str]]


@dataclass
class Pruefung:
    name: str
    ok: bool
    detail: str


@dataclass
class HealthErgebnis:
    pruefungen: list[Pruefung] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(p.ok for p in self.pruefungen)

    @property
    def probleme(self) -> list[str]:
        return [f"{p.name}: {p.detail}" for p in self.pruefungen if not p.ok]

    def as_dict(self) -> dict:
        return {"ok": self.ok, "pruefungen": [p.__dict__ for p in self.pruefungen]}


def _zeit(wert: str) -> datetime:
    t = datetime.fromisoformat(wert)
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _alter_h(wert: str | None, jetzt: datetime) -> float | None:
    return None if wert is None else (jetzt - _zeit(wert)).total_seconds() / 3600


def server_url(config: Config) -> str:
    s = config.settings.server
    host = "127.0.0.1" if "127.0.0.1" in s.bind or not s.bind else s.bind[0]
    host = f"[{host}]" if ":" in host else host
    return f"http://{host}:{s.port}/health"


def frage_server(url: str, timeout_s: float) -> tuple[bool, str]:
    try:
        r = httpx.get(url, timeout=timeout_s)
    except httpx.HTTPError as exc:
        return False, f"keine Antwort von {url} ({type(exc).__name__})"
    if r.status_code != 200:
        return False, f"{url} antwortet mit HTTP {r.status_code}"
    try:
        ok = r.json().get("ok") is True
    except ValueError:
        ok = False
    return (True, "antwortet") if ok else (False, f"{url} meldet nicht ok")


def _letzter(conn: sqlite3.Connection, schritt: str) -> tuple[str | None, sqlite3.Row | None]:
    """(Start des letzten fehlerfreien Eintrags, letzter Eintrag überhaupt)."""
    ok = conn.execute("SELECT MAX(start) FROM run_log WHERE schritt = ? AND fehler IS NULL", (schritt,)).fetchone()[0]
    letzter = conn.execute("SELECT start, fehler FROM run_log WHERE schritt = ? ORDER BY id DESC LIMIT 1", (schritt,)).fetchone()
    return ok, letzter


def _alters_pruefung(conn: sqlite3.Connection, schritt: str, max_h: int, jetzt: datetime) -> Pruefung:
    ok_start, letzter = _letzter(conn, schritt)
    alter = _alter_h(ok_start, jetzt)
    if alter is None:
        return Pruefung(schritt, False, "noch nie fehlerfrei gelaufen")
    detail = f"zuletzt fehlerfrei vor {alter:.1f} h (Grenze {max_h} h)"
    if letzter is not None and letzter["fehler"]:
        detail += f"; letzter Versuch mit Fehler: {letzter['fehler'].splitlines()[0][:200]}"
    return Pruefung(schritt, alter <= max_h, detail)


def pruefe(conn: sqlite3.Connection, config: Config, *, jetzt: datetime | None = None,
           server_abfrage: ServerAbfrage | None = frage_server) -> HealthErgebnis:
    """`server_abfrage=None` lässt die Server-Prüfung aus (z. B. wenn der Server selbst fragt)."""
    h = config.settings.health
    jetzt = jetzt or datetime.now(UTC)
    erg = HealthErgebnis()

    for portal in h.portale:
        neuestes = conn.execute("SELECT MAX(first_seen) FROM listing WHERE provider = ?", (portal,)).fetchone()[0]
        alter = _alter_h(neuestes, jetzt)
        if alter is None:
            erg.pruefungen.append(Pruefung(f"portal:{portal}", False, "noch nie ein Angebot geliefert"))
        else:
            tage = alter / 24
            erg.pruefungen.append(Pruefung(f"portal:{portal}", tage <= h.max_tage_ohne_angebot,
                                           f"neuestes Angebot vor {tage:.1f} Tagen (Grenze {h.max_tage_ohne_angebot})"))

    erg.pruefungen.append(_alters_pruefung(conn, "sync", h.max_stunden_ohne_sync, jetzt))
    erg.pruefungen.append(_alters_pruefung(conn, "backup", h.max_stunden_ohne_backup, jetzt))

    if server_abfrage is not None:
        ok, detail = server_abfrage(server_url(config), h.server_timeout_s)
        erg.pruefungen.append(Pruefung("server", ok, detail))
    return erg


def protokolliere(conn: sqlite3.Connection, erg: HealthErgebnis, start: str) -> None:
    conn.execute(
        "INSERT INTO run_log (schritt, start, ende, zahlen_json, fehler) VALUES ('health', ?, ?, ?, ?)",
        (start, now_iso(), json.dumps(erg.as_dict(), ensure_ascii=False), "\n".join(erg.probleme) or None),
    )
    conn.commit()
