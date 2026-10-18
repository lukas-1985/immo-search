"""Konfigurations-Editor: prüfen → Diff → Backup → schreiben → protokollieren.

Geschrieben wird nur in `config/` (settings.yaml und profiles/<id>.yaml). Vor jedem Schreiben wird die
komplette Konfiguration in einer Kopie geladen und geprüft (Pydantic + Feldnamen/KPIs der Profile).
Kommentare und Reihenfolge bleiben erhalten (ruamel.yaml, Rundlauf).
"""

from __future__ import annotations

import difflib
import io
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from .config import ConfigError, load_config
from .db import now_iso

_DATEI = re.compile(r"^(settings\.yaml|profiles/[a-z0-9][a-z0-9-]*\.yaml)$")


class EditFehler(ValueError):
    pass


def pruefe_pfad(rel: str) -> str:
    rel = rel.replace("\\", "/").strip()
    if not _DATEI.match(rel):
        raise EditFehler(f"Datei nicht erlaubt: {rel!r} (nur settings.yaml und profiles/<id>.yaml)")
    return rel


def dateien(config_dir: Path) -> list[str]:
    return ["settings.yaml"] + [f"profiles/{p.name}" for p in sorted((config_dir / "profiles").glob("*.yaml"))]


def lesen(config_dir: Path, rel: str) -> str:
    p = config_dir / pruefe_pfad(rel)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def pruefe(config_dir: Path, aenderungen: dict[str, str | None]) -> list[str]:
    """Lädt die Konfiguration mit den Änderungen in einer Kopie. Leere Liste = in Ordnung.

    `aenderungen`: rel → neuer Inhalt (None = Datei löschen).
    """
    from .scoring import pruefe_profil  # spät importieren (Zyklus vermeiden)

    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "config"
        shutil.copytree(config_dir, kopie, ignore=shutil.ignore_patterns(".history"))
        for rel, text in aenderungen.items():
            ziel = kopie / pruefe_pfad(rel)
            if text is None:
                ziel.unlink(missing_ok=True)
            else:
                ziel.parent.mkdir(parents=True, exist_ok=True)
                ziel.write_text(text, encoding="utf-8")
        try:
            cfg = load_config(kopie)
            for p in cfg.profiles.values():
                pruefe_profil(p)
        except ConfigError as exc:
            return [str(exc).replace(str(kopie), "config")]
    return []


def diff(alt: str, neu: str, rel: str) -> str:
    return "".join(difflib.unified_diff(alt.splitlines(keepends=True), neu.splitlines(keepends=True),
                                        fromfile=f"{rel} (alt)", tofile=f"{rel} (neu)"))


def _backup(config_dir: Path, rel: str) -> Path | None:
    quelle = config_dir / rel
    if not quelle.exists():
        return None
    ziel_dir = config_dir / ".history"
    ziel_dir.mkdir(exist_ok=True)
    ziel = ziel_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}__{rel.replace('/', '__')}"
    shutil.copy2(quelle, ziel)
    return ziel


def speichern(conn: sqlite3.Connection, config_dir: Path, rel: str, text: str | None) -> dict[str, Any]:
    """Prüfen, sichern, schreiben, protokollieren. `text=None` löscht die Datei (nur Profile)."""
    rel = pruefe_pfad(rel)
    if text is None and rel == "settings.yaml":
        raise EditFehler("settings.yaml kann nicht gelöscht werden")
    alt = lesen(config_dir, rel)
    neu = "" if text is None else text.replace("\r\n", "\n")
    if text is not None and alt == neu:
        return {"geaendert": False, "diff": ""}
    fehler = pruefe(config_dir, {rel: None if text is None else neu})
    if fehler:
        raise EditFehler("\n".join(fehler))
    d = diff(alt, neu, rel)
    backup = _backup(config_dir, rel)
    ziel = config_dir / rel
    if text is None:
        ziel.unlink()
    else:
        ziel.write_text(neu, encoding="utf-8", newline="\n")
    conn.execute("INSERT INTO config_change (datei, diff, backup_pfad, zeitpunkt) VALUES (?, ?, ?, ?)",
                 (rel, d, str(backup) if backup else None, now_iso()))
    conn.commit()
    return {"geaendert": True, "diff": d, "backup": str(backup) if backup else None}


def backups(config_dir: Path, rel: str | None = None) -> list[dict[str, str]]:
    d = config_dir / ".history"
    out = []
    for p in sorted(d.glob("*__*"), reverse=True) if d.exists() else []:
        stamp, _, rest = p.name.partition("__")
        datei = rest.replace("__", "/")
        if rel is None or datei == rel:
            out.append({"name": p.name, "datei": datei, "zeitpunkt": stamp})
    return out


def backup_lesen(config_dir: Path, name: str) -> tuple[str, str]:
    if "/" in name or "\\" in name or ".." in name:
        raise EditFehler("ungültiger Backup-Name")
    p = config_dir / ".history" / name
    if not p.exists():
        raise EditFehler("Backup nicht gefunden")
    return pruefe_pfad(name.partition("__")[2].replace("__", "/")), p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- YAML-Rundlauf für gezielte Änderungen


def yaml_skalar(wert: Any) -> str:
    if wert is None:
        return "null"
    if isinstance(wert, bool):
        return "true" if wert else "false"
    if isinstance(wert, int | float):
        return repr(int(wert)) if float(wert).is_integer() and not isinstance(wert, float) else repr(float(wert))
    if isinstance(wert, list):
        return "[" + ", ".join(yaml_skalar(v) for v in wert) + "]"
    out = io.StringIO()
    YAML(typ="safe", pure=True).dump(str(wert), out)
    return out.getvalue().strip().removesuffix("...").strip()


def _token_ende(zeile: str, start: int) -> int:
    """Ende eines skalaren Werts ab `start` (Block- oder Flow-Stil, mit Anführungszeichen)."""
    if start < len(zeile) and zeile[start] in "\"'":
        q = zeile[start]
        i = start + 1
        while i < len(zeile):
            if zeile[i] == q and not (q == '"' and zeile[i - 1] == "\\"):
                return i + 1
            i += 1
        return len(zeile)
    i = start
    while i < len(zeile):
        c = zeile[i]
        if c in ",}]" or (c == "#" and i > 0 and zeile[i - 1] in " \t"):
            break
        i += 1
    return len(zeile[:i].rstrip())


def _setze_einen(text: str, pfad: tuple, wert: Any) -> str:
    data = YAML().load(text) or {}
    knoten = data
    for k in pfad[:-1]:
        try:
            knoten = knoten[k]
        except (KeyError, IndexError, TypeError) as exc:
            raise EditFehler(f"Pfad {'.'.join(map(str, pfad))} gibt es in der Datei nicht") from exc
    key = pfad[-1]
    zeilen = text.split("\n")
    if key in knoten:
        z, s = knoten.lc.value(key)
        if isinstance(knoten[key], dict | list) and not isinstance(wert, list):
            raise EditFehler(f"{'.'.join(map(str, pfad))} ist kein einzelner Wert")
        if isinstance(knoten[key], list):  # Flow-Liste [..] als Ganzes ersetzen
            ende = zeilen[z].index("]", s) + 1
        else:
            ende = _token_ende(zeilen[z], s)
        zeilen[z] = zeilen[z][:s] + yaml_skalar(wert) + zeilen[z][ende:]
        return "\n".join(zeilen)
    # neuer Schlüssel: als letzte Zeile des (Block-)Abschnitts einfügen
    if not knoten or getattr(knoten, "fa", None) is not None and knoten.fa.flow_style():
        raise EditFehler(f"{'.'.join(map(str, pfad))}: Einfügen hier nicht möglich, bitte im YAML-Modus ergänzen")
    letzter = list(knoten.keys())[-1]
    z, einzug = knoten.lc.key(letzter)
    ziel = z + 1
    while ziel < len(zeilen):
        inhalt = zeilen[ziel].strip()
        if inhalt and not inhalt.startswith("#") and len(zeilen[ziel]) - len(zeilen[ziel].lstrip()) <= einzug:
            break
        ziel += 1
    while ziel > z + 1 and not zeilen[ziel - 1].strip():
        ziel -= 1
    zeilen.insert(ziel, " " * einzug + f"{key}: {yaml_skalar(wert)}")
    return "\n".join(zeilen)


def setze_werte(text: str, werte: dict[tuple, Any]) -> str:
    """Setzt Werte an Pfaden (Tupel aus Schlüsseln/Indizes) direkt im Text: Kommentare, Einrückung und
    Schreibweise aller anderen Zeilen bleiben unverändert."""
    for pfad, wert in werte.items():
        text = _setze_einen(text, pfad, wert)
    return text


def profil_kopieren(conn: sqlite3.Connection, config_dir: Path, quelle_id: str, neue_id: str, name: str | None = None) -> dict[str, Any]:
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", neue_id):
        raise EditFehler("Profil-ID: nur Kleinbuchstaben, Ziffern und Bindestrich")
    if (config_dir / "profiles" / f"{neue_id}.yaml").exists():
        raise EditFehler(f"Profil '{neue_id}' gibt es schon")
    text = lesen(config_dir, f"profiles/{quelle_id}.yaml")
    if not text:
        raise EditFehler(f"Profil '{quelle_id}' nicht gefunden")
    neu = setze_werte(text, {("id",): neue_id, ("name",): name or f"Kopie von {quelle_id}", ("active",): False})
    return speichern(conn, config_dir, f"profiles/{neue_id}.yaml", neu)


def profil_aktiv(conn: sqlite3.Connection, config_dir: Path, profil_id: str, aktiv: bool) -> dict[str, Any]:
    rel = f"profiles/{profil_id}.yaml"
    text = lesen(config_dir, rel)
    if not text:
        raise EditFehler(f"Profil '{profil_id}' nicht gefunden")
    return speichern(conn, config_dir, rel, setze_werte(text, {("active",): aktiv}))
