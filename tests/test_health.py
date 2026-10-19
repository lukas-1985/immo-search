import json
from datetime import UTC, datetime, timedelta

import pytest

from immo.config import load_config
from immo.health import protokolliere, pruefe, server_url

JETZT = datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC)


def _iso(stunden_zurueck: float) -> str:
    return (JETZT - timedelta(hours=stunden_zurueck)).isoformat()


def _listing(conn, n, provider, first_seen):
    conn.execute(
        "INSERT INTO listing (provider, url, first_seen, last_seen) VALUES (?, ?, ?, ?)",
        (provider, f"https://example.test/{n}", first_seen, first_seen),
    )


def _log(conn, schritt, start, fehler=None):
    conn.execute("INSERT INTO run_log (schritt, start, fehler) VALUES (?, ?, ?)", (schritt, start, fehler))


@pytest.fixture
def gesund(conn):
    _listing(conn, 1, "immoscout", _iso(5))
    _listing(conn, 2, "immowelt", _iso(48))
    _listing(conn, 3, "kleinanzeigen", _iso(70))
    _log(conn, "sync", _iso(2))
    _log(conn, "backup", _iso(9))
    conn.commit()
    return conn


def _server_ok(url, timeout):
    return True, "antwortet"


def test_alles_gesund(gesund, config):
    erg = pruefe(gesund, config, jetzt=JETZT, server_abfrage=_server_ok)
    assert erg.ok, erg.probleme
    assert [p.name for p in erg.pruefungen] == ["portal:immoscout", "portal:immowelt", "portal:kleinanzeigen",
                                                "sync", "backup", "server"]


def test_portal_stumm_und_portal_ohne_angebote(conn, config):
    _listing(conn, 1, "immoscout", _iso(1))
    _listing(conn, 2, "immowelt", _iso(4 * 24))  # älter als 3 Tage
    conn.commit()
    erg = pruefe(conn, config, jetzt=JETZT, server_abfrage=None)
    status = {p.name: p.ok for p in erg.pruefungen}
    assert status["portal:immoscout"] and not status["portal:immowelt"] and not status["portal:kleinanzeigen"]
    assert "server" not in status
    assert any("kleinanzeigen: noch nie" in p for p in erg.probleme)


def test_sync_alt_und_letzter_mit_fehler(gesund, config):
    _log(gesund, "sync", _iso(1), fehler="Fredy nicht erreichbar\nDetails")
    gesund.execute("UPDATE run_log SET start = ? WHERE schritt = 'sync' AND fehler IS NULL", (_iso(13),))
    erg = pruefe(gesund, config, jetzt=JETZT, server_abfrage=_server_ok)
    sync = next(p for p in erg.pruefungen if p.name == "sync")
    assert not sync.ok and "13.0 h" in sync.detail and "Fredy nicht erreichbar" in sync.detail


def test_backup_fehlt_und_server_antwortet_nicht(conn, config):
    erg = pruefe(conn, config, jetzt=JETZT, server_abfrage=lambda url, t: (False, f"keine Antwort von {url}"))
    status = {p.name: p for p in erg.pruefungen}
    assert status["backup"].detail == "noch nie fehlerfrei gelaufen"
    assert not status["server"].ok and "127.0.0.1:8710/health" in status["server"].detail


def test_grenzwerte_aus_settings(tmp_path):
    d = tmp_path / "config"
    (d / "profiles").mkdir(parents=True)
    (d / "settings.yaml").write_text(
        'server: { bind: ["100.1.2.3"], port: 9000 }\n'
        "health: { portale: [immoscout], max_tage_ohne_angebot: 1 }\n", encoding="utf-8")
    config = load_config(d)
    assert server_url(config) == "http://100.1.2.3:9000/health"
    assert config.settings.health.portale == ["immoscout"]


def test_protokoll_in_run_log(gesund, config):
    erg = pruefe(gesund, config, jetzt=JETZT, server_abfrage=lambda url, t: (False, "weg"))
    protokolliere(gesund, erg, _iso(0))
    row = gesund.execute("SELECT zahlen_json, fehler FROM run_log WHERE schritt = 'health'").fetchone()
    assert row["fehler"] == "server: weg"
    daten = json.loads(row["zahlen_json"])
    assert daten["ok"] is False and len(daten["pruefungen"]) == 6
