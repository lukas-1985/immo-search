import json
import sqlite3
from pathlib import Path

import pytest

from immo.codex_extraktion import cli_fehlertext, codex_antwort, extrahiere, finde_codex, normalisiere
from immo.db import SCHEMA_V1, SCHEMA_V2, connect
from immo.extraction import field_values
from immo.ki_io import pending, save
from .test_extraction import seeded, _result


def antwort(angebote, **kwargs):
    return {"ergebnisse": [dict(listing_id=a["listing_id"], beschreibung_hash=a["beschreibung_hash"],
                                  felder=[]) for a in angebote]}


def test_migration_erhaelt_claude(tmp_path):
    path = tmp_path / "alt.db"
    c = sqlite3.connect(path)
    c.executescript(SCHEMA_V1 + SCHEMA_V2 + "PRAGMA user_version=2;")
    c.execute("INSERT INTO listing (id, provider, url, first_seen, last_seen) VALUES (1, 'x', 'x', 'x', 'x')")
    c.execute("INSERT INTO extraction VALUES (1, 'provision', '0', 'claude', 'hoch', 'x', 1, 'x')")
    c.execute("INSERT INTO extraction_status VALUES (1, 'hash', 1, 'ok', 0, NULL, 'x')")
    c.commit()
    c.close()
    c = connect(path)
    assert c.execute("PRAGMA user_version").fetchone()[0] == 3
    assert c.execute("SELECT quelle FROM extraction").fetchone()[0] == "claude"
    assert c.execute("SELECT status FROM extraction_status").fetchone()[0] == "ok"
    assert not c.execute("PRAGMA foreign_key_check").fetchall()
    c.close()


def test_quellenwechsel_entfernt_alte_ki_felder(seeded):
    c, config, _ = seeded
    result = _result(c, 8, {"heizungsart": {"wert": "Gas", "konfidenz": "hoch", "belegstelle": "Gas-Etagenheizungen"}})
    save(c, config, {"ergebnisse": [result]}, quelle="claude")
    assert field_values(c, result["listing_id"])["heizungsart"]["quelle"] == "claude"
    result["felder"] = {}
    save(c, config, {"ergebnisse": [result]}, modell="test-modell")
    assert "heizungsart" not in field_values(c, result["listing_id"])
    assert c.execute("SELECT modell FROM extraction_run ORDER BY id DESC").fetchone()[0] == "test-modell"


@pytest.mark.parametrize("art", ["fremde_id", "hash", "fehlend", "doppelt", "fremdes_feld"])
def test_transport_verwirft_fremde_oder_unvollstaendige_antworten(art):
    vorlage = [{"listing_id": 1, "beschreibung_hash": "hash", "gesucht": ["provision"]}]
    data = antwort(vorlage)
    if art == "fremde_id":
        data["ergebnisse"][0]["listing_id"] = 2
    elif art == "hash":
        data["ergebnisse"][0]["beschreibung_hash"] = "alt"
    elif art == "fehlend":
        data["ergebnisse"] = []
    elif art == "doppelt":
        data["ergebnisse"] *= 2
    else:
        data["ergebnisse"][0]["felder"] = [dict(feld="falsch", wert_json="0", konfidenz="hoch", belegstelle="x", rechenweg=None)]
    with pytest.raises(ValueError):
        normalisiere(data, vorlage)


def test_lauf_verarbeitet_alle_stapel_und_wiederholt_nicht(seeded, tmp_path):
    c, config, _ = seeded
    config.settings.ki.stapelgroesse = 5
    aufrufe = []
    def fake(angebote, modell, timeout, log):
        aufrufe.append(angebote)
        return dict(antwort(angebote), _modell="tatsaechliches-modell")
    result = extrahiere(c, config, antwort_fn=fake, ausgabe_dir=tmp_path / "extraction")
    assert result["angenommen"] == 12 and result["offen"] == 0
    assert [len(a) for a in aufrufe] == [5, 5, 2]
    assert result["modell"] == "tatsaechliches-modell"
    assert c.execute("SELECT DISTINCT modell FROM extraction_run").fetchone()[0] == "tatsaechliches-modell"
    extrahiere(c, config, antwort_fn=fake, ausgabe_dir=tmp_path / "extraction")
    assert len(aufrufe) == 3


def test_ki_ausfall_bleibt_offen_und_wird_protokolliert(seeded, tmp_path):
    c, config, _ = seeded
    def fake(*args):
        raise ValueError("Nutzungslimit")
    with pytest.raises(ValueError, match="Nutzungslimit"):
        extrahiere(c, config, antwort_fn=fake, ausgabe_dir=tmp_path / "extraction")
    assert pending(c, config)["offen_gesamt"] == 12
    assert c.execute("SELECT fehler FROM run_log WHERE schritt='ki'").fetchone()[0] == "Nutzungslimit"


def test_fachfehler_nur_einmal_korrigieren(seeded, tmp_path):
    c, config, _ = seeded
    lid = pending(c, config)["angebote"][0]["listing_id"]
    aufrufe = []
    def fake(angebote, *args):
        aufrufe.append(angebote)
        data = antwort(angebote)
        data["ergebnisse"][0]["felder"] = [dict(feld="risiken", wert_json='"keine Liste"',
                                                   konfidenz="hoch", belegstelle="x", rechenweg=None)]
        return data
    result = extrahiere(c, config, listing_id=lid, reextract=True, antwort_fn=fake, ausgabe_dir=tmp_path / "extraction")
    assert len(aufrufe) == 2 and result["abgelehnt"] == 1
    assert c.execute("SELECT versuche FROM extraction_status WHERE listing_id=?", (lid,)).fetchone()[0] == 2


def test_codex_fehlt_mit_verstaendlicher_meldung(monkeypatch, tmp_path):
    monkeypatch.setattr("immo.codex_extraktion.shutil.which", lambda name: None)
    monkeypatch.setattr("immo.codex_extraktion.installationsordner", lambda: [tmp_path])
    with pytest.raises(ValueError, match="Codex CLI nicht gefunden"):
        codex_antwort([], None, 30, tmp_path / "log")


def test_codex_pfad_hat_vorrang_und_fehler_wird_nicht_verschluckt(monkeypatch, tmp_path):
    monkeypatch.setattr("immo.codex_extraktion.shutil.which", lambda name: "andere-codex.exe")
    programm = tmp_path / "Ordner mit Leerzeichen" / "codex.exe"
    programm.parent.mkdir()
    programm.touch()
    assert finde_codex(str(programm)) == str(programm.resolve())
    with pytest.raises(ValueError, match="ki.cli_pfad"):
        finde_codex(str(tmp_path / "fehlt.exe"))


@pytest.mark.parametrize("unterordner", ["Programs/OpenAI/Codex/bin", "OpenAI/Codex/bin/version-1"])
def test_codex_ohne_desktop_path(monkeypatch, tmp_path, unterordner):
    monkeypatch.setattr("immo.codex_extraktion.shutil.which", lambda name: None)
    monkeypatch.setattr("immo.codex_extraktion.installationsordner", lambda: [tmp_path])
    programm = tmp_path / unterordner / "codex.exe"
    programm.parent.mkdir(parents=True)
    programm.touch()
    assert finde_codex() == str(programm)


def test_codex_cache_nimmt_neueste_version(monkeypatch, tmp_path):
    import os
    monkeypatch.setattr("immo.codex_extraktion.shutil.which", lambda name: None)
    monkeypatch.setattr("immo.codex_extraktion.installationsordner", lambda: [tmp_path])
    for name, zeit in (("alt", 1), ("neu", 2)):
        programm = tmp_path / "OpenAI/Codex/bin" / name / "codex.exe"
        programm.parent.mkdir(parents=True)
        programm.touch()
        os.utime(programm, (zeit, zeit))
    assert Path(finde_codex()).parent.name == "neu"


def test_extraktion_reicht_cli_pfad_weiter(seeded, monkeypatch, tmp_path):
    c, config, _ = seeded
    config.settings.ki.cli_pfad = "gewaehlte-codex.exe"
    gesehen = []
    def fake(angebote, modell, timeout, log, *, cli_pfad):
        gesehen.append(cli_pfad)
        return antwort(angebote)
    monkeypatch.setattr("immo.codex_extraktion.codex_antwort", fake)
    extrahiere(c, config, ausgabe_dir=tmp_path / "extraction")
    assert gesehen == ["gewaehlte-codex.exe"]


def test_cli_fehler_erscheint_im_laufprotokoll(tmp_path):
    log = tmp_path / "codex.log"
    log.write_text("user\nPrompt\nERROR: Selected model is at capacity. Please try a different model.\n", encoding="utf-8")
    assert "ausgelastet" in cli_fehlertext(log)
    log.write_text("Error: Anmeldung fehlt\n", encoding="utf-8")
    assert cli_fehlertext(log) == "Error: Anmeldung fehlt"


def test_runner_reicht_testkontext_weiter(config, tmp_path):
    from immo.jobs import befehl
    db = tmp_path / "test.db"
    for typ in ("lauf", "bewerten", "neu_auswerten"):
        cmd = befehl(config, typ, {"listing_id": 1}, db)
        assert str(db) in cmd and str(config.config_dir) in cmd


@pytest.mark.parametrize("korrigiert", [True, False])
def test_gastherme_formatfehler_korrigiert_nur_betroffenes_angebot(seeded, tmp_path, korrigiert):
    c, config, _ = seeded
    lid = _result(c, 2, {})["listing_id"]
    c.execute("UPDATE listing SET beschreibung = beschreibung || ' Eine Gastherme ist vorhanden.' WHERE id=?", (lid,))
    c.execute("INSERT INTO extraction VALUES (?, 'heizungsart', ?, 'claude', 'hoch', 'alt', 1, 'alt')",
              (lid, json.dumps("Alte Heizung")))
    c.commit()
    aufrufe = []

    def fake(angebote, *args):
        aufrufe.append([a["listing_id"] for a in angebote])
        if len(aufrufe) == 2:
            assert aufrufe[-1] == [lid]
            assert "heizungsart" in angebote[0]["letzter_fehler"][0]
            assert c.execute("SELECT count(*) FROM extraction_status WHERE status='ok'").fetchone()[0] == 11
            assert field_values(c, lid)["heizungsart"]["wert"] == "Alte Heizung"
        data = antwort(angebote)
        betroffen = next(r for r in data["ergebnisse"] if r["listing_id"] == lid)
        betroffen["felder"] = [dict(feld="heizungsart",
            wert_json=json.dumps("Gastherme") if korrigiert and len(aufrufe) == 2 else "Gastherme",
            konfidenz="hoch", belegstelle="Eine Gastherme ist vorhanden.", rechenweg=None)]
        return data

    ausgabe = tmp_path / "extraction"
    result = extrahiere(c, config, antwort_fn=fake, ausgabe_dir=ausgabe)
    assert len(aufrufe) == 2
    assert result["angenommen"] == (12 if korrigiert else 11)
    assert result["abgelehnt"] == (0 if korrigiert else 1)
    assert result["offen"] == (0 if korrigiert else 1)
    assert len(list(ausgabe.glob("*.antwort.json"))) == 2
    status = c.execute("SELECT status, versuche FROM extraction_status WHERE listing_id=?", (lid,)).fetchone()
    assert tuple(status) == (("ok", 0) if korrigiert else ("fehler", 2))
    assert field_values(c, lid)["heizungsart"]["wert"] == ("Gastherme" if korrigiert else "Alte Heizung")


def test_fremde_id_verhindert_speicherung_des_stapels(seeded, tmp_path):
    c, config, _ = seeded
    def fake(angebote, *args):
        data = antwort(angebote)
        data["ergebnisse"][-1]["listing_id"] = 99999
        return data
    with pytest.raises(ValueError, match="Angebots-IDs"):
        extrahiere(c, config, antwort_fn=fake, ausgabe_dir=tmp_path / "extraction")
    assert c.execute("SELECT count(*) FROM extraction_run").fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM extraction_status").fetchone()[0] == 0
