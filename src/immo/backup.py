"""Tägliches Backup: eigene DB, config/ und Fredys DB-Ordner, mit Aufbewahrungsfrist.

Ziel: <backup.ziel>/immo-JJJJMMTT-HHMMSS/
  immo.db    Online-Backup über die SQLite-Backup-API (konsistent, auch während eines Laufs)
  config/    Kopie von config/ (samt .history/)
  fredy/     Fredys DB-Ordner, SQLite-Dateien als geprüfter Schnappschuss

Fredys Dateien werden nur gelesen. Über die Grenze Docker/Windows sind SQLite-Sperren nicht verlässlich,
deshalb wird nicht die Original-DB geöffnet: Erst werden DB und `-wal` roh kopiert, dann wird die Kopie
geprüft (`integrity_check`) und zu einer Datei verdichtet. Ist der Schnappschuss inkonsistent (Fredy hat
mitten im Kopieren geschrieben), wird neu kopiert.

Ein Backup entsteht zuerst unter `….unvollstaendig` und wird erst am Ende umbenannt. Gezählt und
aufgeräumt werden nur vollständige Backups.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .config import Config

NAME_FORMAT = "immo-%Y%m%d-%H%M%S"
NAME_RE = re.compile(r"^immo-(\d{8}-\d{6})$")
UNVOLLSTAENDIG = ".unvollstaendig"
SQLITE_ENDUNGEN = {".db", ".sqlite", ".sqlite3"}
SQLITE_BEIWERK = ("-wal", "-shm", "-journal")


class BackupFehler(Exception):
    pass


@dataclass
class BackupErgebnis:
    pfad: str
    bytes: int = 0
    dateien: int = 0
    fredy: str = "nicht konfiguriert"
    geloescht: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def integritaet(pfad: Path) -> str:
    conn = sqlite3.connect(pfad)
    try:
        return ";".join(r[0] for r in conn.execute("PRAGMA integrity_check"))
    finally:
        conn.close()


def sichere_sqlite(quelle: Path, ziel: Path) -> None:
    """Online-Backup einer DB, auf die nur diese Seite (Windows) zugreift."""
    src = sqlite3.connect(quelle, timeout=30)
    dst = sqlite3.connect(ziel)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = DELETE")  # Backup als einzelne Datei, ohne -wal
    finally:
        dst.close()
        src.close()
    pruefung = integritaet(ziel)
    if pruefung != "ok":
        raise BackupFehler(f"{ziel.name}: integrity_check meldet {pruefung[:200]}")


def schnappschuss_fremd(quelle: Path, ziel: Path, versuche: int = 3, pause_s: float = 2.0) -> None:
    """Schnappschuss einer fremden SQLite-DB, ohne sie zu öffnen (nur lesen und kopieren)."""
    tmp = ziel.parent / f".tmp-{ziel.name}"
    letzter = ""
    for versuch in range(versuche):
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        kopie = tmp / quelle.name
        try:
            shutil.copy2(quelle, kopie)
            wal = quelle.with_name(quelle.name + "-wal")
            if wal.exists():
                shutil.copy2(wal, tmp / wal.name)
            letzter = integritaet(kopie)  # wendet die WAL auf die Kopie an
            if letzter == "ok":
                sichere_sqlite(kopie, ziel)
                return
        except sqlite3.DatabaseError as exc:
            letzter = str(exc)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if versuch + 1 < versuche:
            time.sleep(pause_s)
    raise BackupFehler(f"{quelle.name}: kein konsistenter Schnappschuss nach {versuche} Versuchen ({letzter[:200]})")


def sichere_ordner_fremd(quelle: Path, ziel: Path) -> None:
    ziel.mkdir(parents=True, exist_ok=True)
    for eintrag in sorted(quelle.iterdir()):
        if eintrag.is_dir():
            sichere_ordner_fremd(eintrag, ziel / eintrag.name)
        elif eintrag.suffix.lower() in SQLITE_ENDUNGEN:
            schnappschuss_fremd(eintrag, ziel / eintrag.name)
        elif not eintrag.name.endswith(SQLITE_BEIWERK):
            shutil.copy2(eintrag, ziel / eintrag.name)


def vorhandene(wurzel: Path) -> list[tuple[datetime, Path]]:
    """Vollständige Backups, neueste zuerst."""
    if not wurzel.exists():
        return []
    out = []
    for p in wurzel.iterdir():
        m = NAME_RE.match(p.name)
        if p.is_dir() and m:
            out.append((datetime.strptime(m.group(1), "%Y%m%d-%H%M%S"), p))
    return sorted(out, reverse=True)


def aufraeumen(wurzel: Path, aufbewahrung_tage: int, mindestens: int, jetzt: datetime) -> list[str]:
    """Löscht Backups älter als die Frist; die `mindestens` neuesten bleiben immer."""
    grenze = jetzt - timedelta(days=aufbewahrung_tage)
    geloescht = []
    for zeit, pfad in vorhandene(wurzel)[mindestens:]:
        if zeit < grenze:
            shutil.rmtree(pfad)
            geloescht.append(pfad.name)
    # abgebrochene Backups (Absturz, Stromausfall) nach einem Tag entfernen
    for p in wurzel.glob(f"immo-*{UNVOLLSTAENDIG}"):
        if p.is_dir() and datetime.fromtimestamp(p.stat().st_mtime) < jetzt - timedelta(days=1):
            shutil.rmtree(p)
            geloescht.append(p.name)
    return geloescht


def _groesse(pfad: Path) -> tuple[int, int]:
    dateien = [p for p in pfad.rglob("*") if p.is_file()]
    return sum(p.stat().st_size for p in dateien), len(dateien)


def erstelle_backup(config: Config, db_path: Path, *, ziel: Path | None = None, jetzt: datetime | None = None) -> BackupErgebnis:
    einst = config.settings.backup
    jetzt = jetzt or datetime.now()
    wurzel = ziel or config.projekt_pfad(einst.ziel)
    wurzel.mkdir(parents=True, exist_ok=True)
    name = jetzt.strftime(NAME_FORMAT)
    arbeit = wurzel / (name + UNVOLLSTAENDIG)
    if arbeit.exists():
        shutil.rmtree(arbeit)
    arbeit.mkdir()

    ergebnis = BackupErgebnis(pfad=str(wurzel / name))
    if not db_path.exists():
        raise BackupFehler(f"{db_path} fehlt")
    sichere_sqlite(db_path, arbeit / "immo.db")
    shutil.copytree(config.config_dir, arbeit / "config")

    if einst.fredy_db_dir:
        fredy = config.projekt_pfad(einst.fredy_db_dir)
        if not fredy.is_dir():
            ergebnis.fredy = "Ordner fehlt"
            ergebnis.warnungen.append(f"Fredys DB-Ordner {fredy} nicht gefunden – nicht gesichert")
        else:
            try:
                sichere_ordner_fremd(fredy, arbeit / "fredy")
                ergebnis.fredy = "ok"
            except (BackupFehler, OSError) as exc:
                ergebnis.fredy = "Fehler"
                ergebnis.warnungen.append(f"Fredy: {exc}")

    arbeit.rename(wurzel / name)
    ergebnis.bytes, ergebnis.dateien = _groesse(wurzel / name)
    ergebnis.geloescht = aufraeumen(wurzel, einst.aufbewahrung_tage, einst.mindestens_behalten, jetzt)
    return ergebnis
