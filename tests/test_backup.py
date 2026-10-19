import sqlite3
from datetime import datetime, timedelta

import pytest

from immo.backup import NAME_FORMAT, BackupFehler, aufraeumen, erstelle_backup, schnappschuss_fremd, vorhandene
from immo.config import load_config
from immo.db import connect

from .conftest import SETTINGS


def _fredy_db(pfad, n=3):
    """Fredy-ähnliche DB im WAL-Modus, deren letzte Zeilen nur in der -wal stehen."""
    c = sqlite3.connect(pfad)
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA wal_autocheckpoint = 0")
    c.execute("CREATE TABLE listings (id INTEGER PRIMARY KEY, title TEXT)")
    c.executemany("INSERT INTO listings (title) VALUES (?)", [(f"Haus {i}",) for i in range(n)])
    c.commit()
    return c  # offen lassen: sonst wird die WAL beim Schließen eingespielt


@pytest.fixture
def welt(tmp_path):
    projekt = tmp_path / "projekt"
    cfg_dir = projekt / "config"
    (cfg_dir / "profiles").mkdir(parents=True)
    fredy = tmp_path / "fredy-db"
    fredy.mkdir()
    (cfg_dir / "settings.yaml").write_text(
        SETTINGS + f'backup: {{ ziel: "backup", aufbewahrung_tage: 7, mindestens_behalten: 2, fredy_db_dir: "{fredy.as_posix()}" }}\n',
        encoding="utf-8")
    (cfg_dir / ".history").mkdir()
    (cfg_dir / ".history" / "alt.yaml").write_text("x: 1", encoding="utf-8")
    config = load_config(cfg_dir)
    conn = connect(config.db_path())
    conn.execute("INSERT INTO run_log (schritt, start) VALUES ('sync', '2026-10-19T10:00:00+00:00')")
    conn.commit()
    fredy_conn = _fredy_db(fredy / "listings.db")
    (fredy / "config.json").write_text("{}", encoding="utf-8")
    yield config, conn, fredy, fredy_conn
    fredy_conn.close()
    conn.close()


def test_backup_vollstaendig_waehrend_db_offen(welt):
    config, conn, fredy, _ = welt
    # Änderung, die bei offener Verbindung noch in der WAL der eigenen DB steht
    conn.execute("INSERT INTO run_log (schritt, start) VALUES ('score', '2026-10-19T11:00:00+00:00')")
    conn.commit()
    jetzt = datetime(2026, 10, 19, 3, 0, 0)
    erg = erstelle_backup(config, config.db_path(), jetzt=jetzt)

    ziel = config.config_dir.parent / "backup" / "immo-20261019-030000"
    assert erg.pfad == str(ziel) and erg.warnungen == [] and erg.fredy == "ok"
    b = sqlite3.connect(ziel / "immo.db")
    assert b.execute("SELECT COUNT(*) FROM run_log").fetchone()[0] == 2
    assert b.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    b.close()
    assert (ziel / "config" / "settings.yaml").exists() and (ziel / "config" / ".history" / "alt.yaml").exists()
    # Fredy: Zeilen aus der WAL sind im Schnappschuss, -wal/-shm werden nicht mitkopiert
    f = sqlite3.connect(ziel / "fredy" / "listings.db")
    assert f.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 3
    f.close()
    assert (ziel / "fredy" / "config.json").exists()
    assert not list((ziel / "fredy").glob("*-wal")) and not list((ziel / "fredy").glob("*-shm"))
    assert erg.dateien >= 4 and erg.bytes > 0
    assert not list(ziel.parent.glob("*.unvollstaendig"))


def test_fredy_originale_bleiben_unveraendert(welt):
    config, _, fredy, _ = welt
    vorher = {p.name: p.read_bytes() for p in fredy.iterdir()}
    erstelle_backup(config, config.db_path(), jetzt=datetime(2026, 10, 19, 3, 0, 0))
    assert {p.name: p.read_bytes() for p in fredy.iterdir()} == vorher


def test_fredy_ordner_fehlt_ist_warnung(welt, tmp_path):
    config, _, fredy, fredy_conn = welt
    fredy_conn.close()
    for p in fredy.iterdir():
        p.unlink()
    fredy.rmdir()
    erg = erstelle_backup(config, config.db_path(), jetzt=datetime(2026, 10, 19, 3, 0, 0))
    assert erg.fredy == "Ordner fehlt" and len(erg.warnungen) == 1
    assert (tmp_path / "projekt" / "backup" / "immo-20261019-030000" / "immo.db").exists()


def test_schnappschuss_kaputte_db_scheitert(tmp_path):
    kaputt = tmp_path / "kaputt.db"
    kaputt.write_bytes(b"keine sqlite-datei" * 100)
    with pytest.raises(BackupFehler, match="kein konsistenter Schnappschuss"):
        schnappschuss_fremd(kaputt, tmp_path / "ziel.db", versuche=2, pause_s=0)
    assert not list(tmp_path.glob(".tmp-*"))


def test_aufraeumen_frist_und_mindestanzahl(tmp_path):
    jetzt = datetime(2026, 10, 30, 3, 0, 0)
    for tage in (0, 1, 8, 9, 20):
        (tmp_path / (jetzt - timedelta(days=tage)).strftime(NAME_FORMAT)).mkdir()
    (tmp_path / "anderer-ordner").mkdir()
    geloescht = aufraeumen(tmp_path, aufbewahrung_tage=7, mindestens=2, jetzt=jetzt)
    assert len(geloescht) == 3
    assert [p.name for _, p in vorhandene(tmp_path)] == ["immo-20261030-030000", "immo-20261029-030000"]
    assert (tmp_path / "anderer-ordner").exists()


def test_aufraeumen_behaelt_mindestanzahl_auch_wenn_alt(tmp_path):
    jetzt = datetime(2026, 10, 30, 3, 0, 0)
    for tage in (30, 40, 50):
        (tmp_path / (jetzt - timedelta(days=tage)).strftime(NAME_FORMAT)).mkdir()
    assert len(aufraeumen(tmp_path, aufbewahrung_tage=7, mindestens=2, jetzt=jetzt)) == 1
    assert len(vorhandene(tmp_path)) == 2


def test_backup_raeumt_alte_auf(welt):
    config, *_ = welt
    jetzt = datetime(2026, 10, 19, 3, 0, 0)
    for tage in (1, 2, 30):
        erstelle_backup(config, config.db_path(), jetzt=jetzt - timedelta(days=tage))
    erg = erstelle_backup(config, config.db_path(), jetzt=jetzt)
    assert erg.geloescht == ["immo-20260919-030000"]
    assert len(vorhandene(config.config_dir.parent / "backup")) == 3
