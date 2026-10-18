import json
import re

import pytest
from fastapi.testclient import TestClient

from immo.config import load_config
from immo.db import connect
from immo.jobs import Runner
from immo.scoring import run_score
from immo.server import create_app
from immo.server.auth import hash_passwort
from immo.server.mcp_tools import Werkzeuge
from immo.sync import run_sync

from .conftest import FakeClient, make_listing

SETTINGS = """
grunderwerbsteuer: { BY: 0.035 }
finance_defaults: { zins: 0.038, tilgung: 0.02, notar_grundbuch: 0.02, makler_default: 0.0357, bewirtschaftung_quote: 0.20 }
server:
  public_base_url: "http://immo.test:8710"
  mcp: { enabled: true, write_tools: [set_status, add_note] }
"""

PROFIL = """id: mfh-a
name: "MFH A"
objektart: mehrfamilienhaus
fredy: { jobs: ["Job IS24", "Job KA"] }
hard_filter:
  - { field: erbpacht,      op: "==", value: false, on_missing: keep }
  - { field: bruttorendite, op: ">=", value: 0.04,  on_missing: keep }   # Mindestrendite
scoring:
  kpis:
    bruttorendite: { weight: 1.0, normalize: { type: linear, min: 0.04, max: 0.08 }, on_missing: estimate }
finance: { bundesland: BY, eigenkapital: 200000 }
"""

PASSWORT = "geheim-passwort-123"
TOKEN = "test-token-abc"


@pytest.fixture
def welt(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    (config_dir / "profiles").mkdir(parents=True)
    (config_dir / "settings.yaml").write_text(SETTINGS, encoding="utf-8")
    (config_dir / "profiles" / "mfh-a.yaml").write_text(PROFIL, encoding="utf-8")
    db = tmp_path / "data" / "immo.db"
    monkeypatch.setenv("UI_PASSWORD_HASH", hash_passwort(PASSWORT))
    monkeypatch.setenv("MCP_TOKEN", TOKEN)
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)

    cfg = load_config(config_dir)
    conn = connect(db)
    client = FakeClient({"Job IS24": [make_listing(1, titel="Gutes MFH", preis=900_000, beschreibung="Mieteinnahmen 54.000 € im Jahr"),
                                      make_listing(2, titel="Teures MFH", preis=700_000)], "Job KA": []})
    run_sync(conn, client, cfg)
    ids = {r["fredy_id"]: r["id"] for r in conn.execute("SELECT id, fredy_id FROM listing")}
    for fid, miete in (("f1", 54_000), ("f2", 30_000)):
        conn.execute("INSERT INTO extraction VALUES (?, 'jahresnettokaltmiete_ist', ?, 'claude', 'hoch', 'Mieteinnahmen 54.000 €', 1, '2026-10-18')",
                     (ids[fid], json.dumps(miete)))
    conn.commit()
    run_score(conn, cfg)
    conn.close()
    app = create_app(config_dir, db, runner=False)
    with TestClient(app) as tc:
        yield tc, config_dir, db, ids


def _csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _login(tc) -> str:
    r = tc.get("/login")
    tc.post("/login", data={"csrf": _csrf(r.text), "passwort": PASSWORT, "weiter": "/"}, follow_redirects=False)
    return _csrf(tc.get("/").text)


def test_ohne_anmeldung_umleitung_und_falsches_passwort(welt):
    tc, *_ = welt
    r = tc.get("/angebote", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    csrf = _csrf(tc.get("/login").text)
    r = tc.post("/login", data={"csrf": csrf, "passwort": "falsch"}, follow_redirects=False)
    assert r.headers["location"] == "/login"
    assert tc.get("/", follow_redirects=False).status_code == 303
    assert tc.get("/health").json()["ok"] is True


def test_seiten_nach_anmeldung(welt):
    tc, _, _, ids = welt
    _login(tc)
    assert "Übersicht" in tc.get("/").text
    liste = tc.get("/angebote?sort=preis&dir=asc").text
    assert liste.index("Teures MFH") < liste.index("Gutes MFH")
    assert "Teures MFH" not in tc.get("/angebote?q=Gutes").text
    detail = tc.get(f"/angebot/{ids['f1']}").text
    assert "Kaufpreisempfehlung" in detail and "<mark>Mieteinnahmen 54.000 €</mark>" in detail
    assert tc.get("/angebot/9999").status_code == 404
    for pfad in ("/simulation", "/konfiguration", "/laeufe", "/konfiguration/bearbeiten?datei=profiles/mfh-a.yaml"):
        assert tc.get(pfad).status_code == 200, pfad
    assert tc.get("/konfiguration/bearbeiten?datei=../.env").status_code == 400


def test_status_notiz_und_neu_auswerten(welt):
    tc, _, db, ids = welt
    csrf = _login(tc)
    lid = ids["f1"]
    assert tc.post(f"/angebot/{lid}/status", data={"status": "interessant"}).status_code == 403  # ohne CSRF
    tc.post(f"/angebot/{lid}/status", data={"csrf": csrf, "status": "interessant", "notiz": "anrufen"})
    tc.post(f"/angebot/{lid}/notiz", data={"csrf": csrf, "text": "Dach prüfen"})
    tc.post(f"/angebot/{lid}/neu-auswerten", data={"csrf": csrf})
    tc.post(f"/angebot/{lid}/neu-auswerten", data={"csrf": csrf})  # doppelt → derselbe Job
    conn = connect(db)
    assert conn.execute("SELECT status, updated_by FROM workflow").fetchone()[:] == ("interessant", "ui")
    assert conn.execute("SELECT notiz FROM workflow_history").fetchone()[0] == "anrufen"
    assert conn.execute("SELECT text, quelle FROM note").fetchone()[:] == ("Dach prüfen", "ui")
    assert [tuple(r) for r in conn.execute("SELECT typ, status, ausgeloest_von FROM job")] == [("neu_auswerten", "wartend", "ui")]
    seite = tc.get(f"/angebot/{lid}").text
    assert "Dach prüfen" in seite and "Status: interessant" in seite
    # Ende-Status blendet das Objekt aus der Liste aus
    tc.post(f"/angebot/{lid}/status", data={"csrf": csrf, "status": "verworfen"})
    assert "Gutes MFH" not in tc.get("/angebote").text


def test_simulation_und_uebernahme_ins_profil(welt):
    tc, config_dir, db, ids = welt
    csrf = _login(tc)
    r = tc.post("/simulation", data={"csrf": csrf, "profil": "mfh-a", "aktion": "rechnen", "hf_1": "0.05", "tilgung_einrechnen": "1"})
    assert r.status_code == 200 and "Herausgefallen" in r.text and "Teures MFH" in r.text.split("Herausgefallen")[1]
    r = tc.post("/simulation", data={"csrf": csrf, "profil": "mfh-a", "aktion": "uebernehmen", "hf_1": "0.05", "tilgung_einrechnen": "1"})
    assert "Prüfung bestanden" in r.text and "value: 0.05" in r.text
    # unveränderte Standardwerte (Zins, Tilgung …) landen nicht im Profil
    sim = tc.get("/simulation").text
    felder = dict(re.findall(r'name="(fin_\w+)" value="([^"]*)"', sim))
    r2 = tc.post("/simulation", data={"csrf": csrf, "profil": "mfh-a", "aktion": "rechnen", "tilgung_einrechnen": "1", **felder})
    assert "Keine Änderung" in r2.text
    text = re.search(r'<textarea name="text" hidden>(.*?)</textarea>', r.text, re.S).group(1)
    import html
    text = html.unescape(text)
    assert "# Mindestrendite" in text  # Kommentar bleibt erhalten

    # speichern → Backup, Protokoll, Neubewertung
    alt_hash = connect(db).execute("SELECT config_hash FROM score LIMIT 1").fetchone()[0]
    r = tc.post("/konfiguration/speichern", data={"csrf": csrf, "datei": "profiles/mfh-a.yaml", "text": text}, follow_redirects=True)
    assert "neu bewertet" in r.text
    conn = connect(db)
    assert conn.execute("SELECT datei FROM config_change").fetchone()[0] == "profiles/mfh-a.yaml"
    assert conn.execute("SELECT config_hash FROM score LIMIT 1").fetchone()[0] != alt_hash
    assert conn.execute("SELECT hard_filter_result FROM score WHERE listing_id = ?", (ids["f2"],)).fetchone()[0] == "ausgeschlossen"
    assert list((config_dir / ".history").iterdir())
    assert "value: 0.05" in (config_dir / "profiles" / "mfh-a.yaml").read_text(encoding="utf-8")


def test_ungueltige_konfiguration_wird_nicht_gespeichert(welt):
    tc, config_dir, db, _ = welt
    csrf = _login(tc)
    vorher = (config_dir / "profiles" / "mfh-a.yaml").read_text(encoding="utf-8")
    kaputt = vorher.replace("bruttorendite: { weight", "gibtsnicht: { weight")
    r = tc.post("/konfiguration/pruefen", data={"csrf": csrf, "datei": "profiles/mfh-a.yaml", "text": kaputt})
    assert "nicht gültig" in r.text and "gibtsnicht" in r.text
    r = tc.post("/konfiguration/speichern", data={"csrf": csrf, "datei": "profiles/mfh-a.yaml", "text": kaputt}, follow_redirects=True)
    assert "Nicht gespeichert" in r.text
    assert (config_dir / "profiles" / "mfh-a.yaml").read_text(encoding="utf-8") == vorher
    assert connect(db).execute("SELECT COUNT(*) FROM config_change").fetchone()[0] == 0


def test_job_runner(welt, tmp_path):
    tc, config_dir, db, _ = welt
    csrf = _login(tc)
    tc.post("/laeufe/starten", data={"csrf": csrf, "typ": "lauf", "profil": "mfh-a"})
    aufrufe = []

    def fake(typ, parameter, log_pfad):
        aufrufe.append((typ, parameter))
        log_pfad.write_text("alles gut", encoding="utf-8")
        return True

    runner = Runner(load_config(config_dir), db, ausfuehren=fake)
    assert runner.einen_ausfuehren() is True
    assert runner.einen_ausfuehren() is False
    assert aufrufe == [("lauf", {"profil": "mfh-a"})]
    job = connect(db).execute("SELECT id, status FROM job").fetchone()
    assert job["status"] == "fertig"
    assert tc.get(f"/laeufe/{job['id']}/log").text == "alles gut"


def _mcp(tc, methode, params=None, token=TOKEN, ident=1):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
               "MCP-Protocol-Version": "2025-06-18"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return tc.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": ident, "method": methode, "params": params or {}})


def test_mcp_token_und_werkzeuge(welt):
    tc, _, db, ids = welt
    assert _mcp(tc, "tools/list", token=None).status_code == 401
    assert _mcp(tc, "tools/list", token="falsch").status_code == 401
    init = _mcp(tc, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
    assert init.status_code == 200, init.text
    tools = _mcp(tc, "tools/list", ident=2)
    namen = {t["name"] for t in tools.json()["result"]["tools"]}
    assert {"search_listings", "get_listing", "simulate_scoring", "set_status", "add_note"} <= namen
    assert "start_run" not in namen  # nicht freigeschaltet
    r = _mcp(tc, "tools/call", {"name": "search_listings", "arguments": {"rendite_min": 0.05}}, ident=3).json()
    inhalt = r["result"].get("structuredContent") or json.loads(r["result"]["content"][0]["text"])
    assert [a["titel"] for a in inhalt["angebote"]] == ["Gutes MFH"]
    assert inhalt["angebote"][0]["link"] == f"http://immo.test:8710/angebot/{ids['f1']}"
    r = _mcp(tc, "tools/call", {"name": "set_status", "arguments": {"listing_id": ids["f1"], "status": "angefragt"}}, ident=4)
    assert r.status_code == 200
    assert connect(db).execute("SELECT status, updated_by FROM workflow").fetchone()[:] == ("angefragt", "mcp")


def test_werkzeuge_direkt(welt):
    tc, _, _, ids = welt
    w = Werkzeuge(tc.app.state.zustand)
    assert w.get_listing(ids["f1"])["bewertung"]["score"] == 50.0  # 6,0 % → 50 Punkte
    assert "fehler" in w.get_listing(9999)
    assert w.explain_score(ids["f1"])["kpis"]["bruttorendite"]["punkte"] == pytest.approx(50.0)
    assert "fehler" in w.compare_listings([ids["f1"]])
    assert len(w.compare_listings([ids["f1"], ids["f2"]])["angebote"]) == 2
    sim = w.simulate_scoring(gewichte={"bruttorendite": 2})
    assert sim["anzahl_neu"] == 2 and "nichts gespeichert" in sim["hinweis"]
    assert "fehler" in w.simulate_scoring(gewichte={"gibtsnicht": 1})
    assert "fehler" in w.set_status(ids["f1"], "quatsch")
    assert {"neu", "verworfen"} <= set(w.felder()["status_werte"])
    assert len(w.get_changes(tage=1)["neu"]) == 2
