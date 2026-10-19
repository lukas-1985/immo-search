"""Job-Runner: festgelegte Läufe nacheinander ausführen (ein Lauf gleichzeitig).

Erlaubt sind nur diese Job-Typen, Parameter werden geprüft (keine freien Befehle):
- `lauf`           run.ps1 [-Profil <id>]           Sync → Regeln → Claude-Extraktion → Bewertung
- `neu_auswerten`  run.ps1 -Listing <id> -Reextract  Claude wertet ein Angebot neu aus → Bewertung
- `bewerten`       scripts/score.py                  nur neu bewerten (z. B. nach Konfigurationsänderung)

Der Runner läuft als Thread im Server. `run.ps1` hält zusätzlich eine Sperrdatei, damit sich
zeitgesteuerte Läufe und Läufe aus der Oberfläche nicht überschneiden.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from .config import Config
from .db import connect, now_iso

log = logging.getLogger("immo.jobs")

JobTyp = Literal["lauf", "neu_auswerten", "bewerten"]
Ausloeser = Literal["zeitplan", "ui", "mcp", "cli"]
ZEITLIMIT_S = {"lauf": 60 * 60, "neu_auswerten": 30 * 60, "bewerten": 10 * 60}


class JobFehler(ValueError):
    pass


def projekt_dir(config: Config) -> Path:
    return config.config_dir.parent


def _pruefe_parameter(conn: sqlite3.Connection, config: Config, typ: str, parameter: dict[str, Any] | None) -> dict[str, Any]:
    parameter = dict(parameter or {})
    if typ == "lauf":
        profil = parameter.get("profil")
        if profil is not None and profil not in config.profiles:
            raise JobFehler(f"Unbekanntes Profil '{profil}'")
        parameter = {"profil": profil} if profil else {}
    elif typ == "neu_auswerten":
        try:
            listing_id = int(parameter.get("listing_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise JobFehler("listing_id fehlt oder ist keine Zahl") from exc
        if conn.execute("SELECT 1 FROM listing WHERE id = ?", (listing_id,)).fetchone() is None:
            raise JobFehler(f"Angebot {listing_id} nicht gefunden")
        parameter = {"listing_id": listing_id}
    elif typ == "bewerten":
        parameter = {}
    else:
        raise JobFehler(f"Unbekannter Job-Typ '{typ}'")
    return parameter


def _gleicher(conn: sqlite3.Connection, typ: str, parameter: dict[str, Any]) -> int | None:
    row = conn.execute(
        "SELECT id FROM job WHERE typ = ? AND parameter = ? AND status IN ('wartend', 'läuft')",
        (typ, json.dumps(parameter, sort_keys=True)),
    ).fetchone()
    return None if row is None else row["id"]


def _log_pfad(config: Config, job_id: int) -> Path:
    logdir = projekt_dir(config) / "data" / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    return logdir / f"job-{job_id}.log"


def einreihen(conn: sqlite3.Connection, config: Config, typ: str, parameter: dict[str, Any] | None, ausgeloest_von: Ausloeser) -> int:
    parameter = _pruefe_parameter(conn, config, typ, parameter)
    gleich = _gleicher(conn, typ, parameter)
    if gleich is not None:
        return gleich  # derselbe Job wartet schon oder läuft
    cur = conn.execute(
        "INSERT INTO job (typ, parameter, ausgeloest_von, status) VALUES (?, ?, ?, 'wartend')",
        (typ, json.dumps(parameter, sort_keys=True), ausgeloest_von),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def direkt_ausfuehren(config: Config, db_path: Path, typ: str, parameter: dict[str, Any] | None,
                      ausgeloest_von: Ausloeser, ausfuehren=None) -> tuple[int | None, bool]:
    """Führt einen Job sofort in diesem Prozess aus (Aufgabenplanung), ohne die Warteschlange des Servers.

    Der Job erscheint wie jeder andere unter „Läufe“, mit Log. Er wird gleich als `läuft` angelegt, damit der
    Runner des Servers ihn nicht ebenfalls aufgreift. Läuft derselbe Job schon, passiert nichts: (None, True).
    """
    conn = connect(db_path)
    try:
        parameter = _pruefe_parameter(conn, config, typ, parameter)
        # Reste abgestürzter zeitgesteuerter Läufe (Neustart des PCs) blockieren sonst jeden weiteren
        grenze = (datetime.now(UTC) - timedelta(seconds=2 * ZEITLIMIT_S[typ])).replace(microsecond=0).isoformat()
        conn.execute("UPDATE job SET status = 'fehler', ende = ? WHERE status = 'läuft' AND ausgeloest_von = 'zeitplan' "
                     "AND typ = ? AND start < ?", (now_iso(), typ, grenze))
        if _gleicher(conn, typ, parameter) is not None:
            return None, True
        cur = conn.execute(
            "INSERT INTO job (typ, parameter, ausgeloest_von, status, start) VALUES (?, ?, ?, 'läuft', ?)",
            (typ, json.dumps(parameter, sort_keys=True), ausgeloest_von, now_iso()),
        )
        job_id: int = cur.lastrowid  # type: ignore[assignment]
        log_pfad = _log_pfad(config, job_id)
        conn.execute("UPDATE job SET log_pfad = ? WHERE id = ?", (str(log_pfad), job_id))
        conn.commit()
    finally:
        conn.close()
    try:
        ok = (ausfuehren or Runner(config, db_path)._prozess)(typ, parameter, log_pfad)
    except Exception as exc:  # noqa: BLE001
        with log_pfad.open("a", encoding="utf-8") as f:
            f.write(f"\nFEHLER: {exc}\n")
        ok = False
    conn = connect(db_path)  # neu öffnen: ein Lauf dauert lange, die erste Verbindung soll nichts sperren
    try:
        conn.execute("UPDATE job SET status = ?, ende = ? WHERE id = ?", ("fertig" if ok else "fehler", now_iso(), job_id))
        conn.commit()
    finally:
        conn.close()
    return job_id, ok


def befehl(config: Config, typ: str, parameter: dict[str, Any]) -> list[str]:
    root = projekt_dir(config)
    if typ == "bewerten":
        return [shutil.which("uv") or "uv", "run", "python", str(root / "scripts" / "score.py")]
    ps = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(root / "run.ps1")]
    if typ == "lauf":
        return ps + (["-Profil", parameter["profil"]] if parameter.get("profil") else [])
    if typ == "neu_auswerten":
        return ps + ["-Listing", str(int(parameter["listing_id"])), "-Reextract"]
    raise JobFehler(f"Unbekannter Job-Typ '{typ}'")


def liste(conn: sqlite3.Connection, limit: int = 30) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM job ORDER BY id DESC LIMIT ?", (limit,)):
        d = dict(r)
        d["parameter"] = json.loads(d["parameter"] or "{}")
        d["dauer_s"] = None
        if d["start"] and d["ende"]:
            d["dauer_s"] = int((datetime.fromisoformat(d["ende"]) - datetime.fromisoformat(d["start"])).total_seconds())
        out.append(d)
    return out


def log_text(conn: sqlite3.Connection, job_id: int, max_zeichen: int = 200_000) -> str | None:
    row = conn.execute("SELECT log_pfad FROM job WHERE id = ?", (job_id,)).fetchone()
    if row is None or not row["log_pfad"] or not Path(row["log_pfad"]).exists():
        return None
    text = Path(row["log_pfad"]).read_text(encoding="utf-8", errors="replace")
    return text[-max_zeichen:]


class Runner:
    """Arbeitet die Warteschlange ab. `ausfuehren` ist austauschbar (Tests)."""

    def __init__(self, config: Config, db_path: Path, intervall_s: float = 2.0, ausfuehren=None):
        self.config = config
        self.db_path = db_path
        self.intervall_s = intervall_s
        self.ausfuehren = ausfuehren or self._prozess
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        conn = connect(self.db_path)
        # Beim Neustart des Servers abgebrochene Jobs als Fehler markieren (zeitgesteuerte laufen in eigenem Prozess)
        conn.execute("UPDATE job SET status = 'fehler', ende = ? WHERE status = 'läuft' AND ausgeloest_von != 'zeitplan'",
                     (now_iso(),))
        conn.commit()
        conn.close()
        self._thread = threading.Thread(target=self._schleife, name="immo-jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _schleife(self) -> None:
        while not self._stop.is_set():
            try:
                if not self.einen_ausfuehren():
                    self._stop.wait(self.intervall_s)
            except Exception:  # noqa: BLE001 - der Runner darf nie sterben
                log.exception("Job-Runner-Fehler")
                self._stop.wait(self.intervall_s)

    def einen_ausfuehren(self) -> bool:
        conn = connect(self.db_path)
        try:
            job = conn.execute("SELECT * FROM job WHERE status = 'wartend' ORDER BY id LIMIT 1").fetchone()
            if job is None:
                return False
            log_pfad = _log_pfad(self.config, job["id"])
            conn.execute("UPDATE job SET status = 'läuft', start = ?, log_pfad = ? WHERE id = ?", (now_iso(), str(log_pfad), job["id"]))
            conn.commit()
            parameter = json.loads(job["parameter"] or "{}")
            try:
                ok = self.ausfuehren(job["typ"], parameter, log_pfad)
            except Exception as exc:  # noqa: BLE001
                log_pfad.open("a", encoding="utf-8").write(f"\nFEHLER: {exc}\n")
                ok = False
            conn.execute("UPDATE job SET status = ?, ende = ? WHERE id = ?", ("fertig" if ok else "fehler", now_iso(), job["id"]))
            conn.commit()
            return True
        finally:
            conn.close()

    def _prozess(self, typ: str, parameter: dict[str, Any], log_pfad: Path) -> bool:
        cmd = befehl(self.config, typ, parameter)
        with log_pfad.open("w", encoding="utf-8") as f:
            f.write(f"$ {' '.join(cmd)}\n\n")
            f.flush()
            try:
                p = subprocess.run(cmd, cwd=projekt_dir(self.config), stdout=f, stderr=subprocess.STDOUT,
                                   timeout=ZEITLIMIT_S[typ], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except subprocess.TimeoutExpired:
                f.write(f"\nZEITLIMIT ({ZEITLIMIT_S[typ]} s) überschritten – abgebrochen\n")
                return False
            f.write(f"\nExit-Code: {p.returncode}\n")
            return p.returncode == 0
