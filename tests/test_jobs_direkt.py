from datetime import UTC, datetime, timedelta

import pytest

from immo.db import connect
from immo.jobs import JobFehler, Runner, direkt_ausfuehren, einreihen


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "immo.db"
    connect(p).close()
    return p


def test_zeitgesteuerter_lauf_wird_job_mit_log(config, db_path):
    gesehen = []

    def ausfuehren(typ, parameter, log_pfad):
        conn = connect(db_path)
        gesehen.append((typ, parameter, conn.execute("SELECT status, ausgeloest_von FROM job").fetchone()))
        conn.close()
        log_pfad.write_text("ok", encoding="utf-8")
        return True

    job_id, ok = direkt_ausfuehren(config, db_path, "lauf", {"profil": "mfh-a"}, "zeitplan", ausfuehren)
    assert ok and job_id is not None
    typ, parameter, waehrenddessen = gesehen[0]
    assert typ == "lauf" and parameter == {"profil": "mfh-a"}
    assert tuple(waehrenddessen) == ("läuft", "zeitplan")
    conn = connect(db_path)
    job = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
    assert job["status"] == "fertig" and job["ende"] and job["log_pfad"].endswith(f"job-{job_id}.log")
    conn.close()


def test_fehler_und_ausnahme_werden_fehler(config, db_path):
    _, ok = direkt_ausfuehren(config, db_path, "lauf", None, "zeitplan", lambda *a: False)
    assert not ok

    def kaputt(*a):
        raise RuntimeError("weg")

    job_id, ok = direkt_ausfuehren(config, db_path, "lauf", {"profil": "mfh-a"}, "zeitplan", kaputt)
    conn = connect(db_path)
    assert not ok and conn.execute("SELECT status FROM job WHERE id = ?", (job_id,)).fetchone()[0] == "fehler"
    conn.close()


def test_unbekanntes_profil(config, db_path):
    with pytest.raises(JobFehler):
        direkt_ausfuehren(config, db_path, "lauf", {"profil": "gibt-es-nicht"}, "zeitplan", lambda *a: True)


def test_laufender_gleicher_job_wird_uebersprungen_alte_reste_nicht(config, db_path):
    conn = connect(db_path)
    einreihen(conn, config, "lauf", None, "ui")  # wartet beim Server
    assert direkt_ausfuehren(config, db_path, "lauf", None, "zeitplan", lambda *a: pytest.fail("darf nicht laufen")) == (None, True)
    conn.execute("DELETE FROM job")
    alt = (datetime.now(UTC) - timedelta(hours=5)).replace(microsecond=0).isoformat()
    conn.execute("INSERT INTO job (typ, parameter, ausgeloest_von, status, start) VALUES ('lauf', '{}', 'zeitplan', 'läuft', ?)", (alt,))
    conn.commit()
    job_id, ok = direkt_ausfuehren(config, db_path, "lauf", None, "zeitplan", lambda *a: True)
    assert ok and job_id is not None
    assert conn.execute("SELECT status FROM job WHERE start = ?", (alt,)).fetchone()[0] == "fehler"
    conn.close()


def test_server_neustart_laesst_zeitgesteuerte_laeufe_in_ruhe(config, db_path):
    conn = connect(db_path)
    conn.execute("INSERT INTO job (typ, parameter, ausgeloest_von, status, start) VALUES ('lauf', '{}', 'zeitplan', 'läuft', 'x')")
    conn.execute("INSERT INTO job (typ, parameter, ausgeloest_von, status, start) VALUES ('bewerten', '{}', 'ui', 'läuft', 'x')")
    conn.commit()
    r = Runner(config, db_path, ausfuehren=lambda *a: True)
    r.start()
    r.stop()
    status = dict(conn.execute("SELECT ausgeloest_von, status FROM job").fetchall())
    assert status == {"zeitplan": "läuft", "ui": "fehler"}
    conn.close()
