"""Objekt-Simulation (Phase 8b): Zielwert-Rückrechnung gegen Handrechnung und Zufallsfälle, Szenarien, Oberfläche."""

import json
import math
import random

import pytest

from immo import objekt_simulation as osim
from immo.config import load_config
from immo.db import connect
from immo.finance import ZIEL_GROESSEN, loese, simulate

from .test_finance import A, approx
from .test_server import _login, welt  # noqa: F401  (Fixture)

# --------------------------------------------------------------------------- finance.loese


def _kennzahl(e, ziel):
    return {"cashflow_monat": e.cashflow_monat, "bruttorendite": e.bruttorendite, "nettoanfangsrendite": e.nettoanfangsrendite}[ziel]


@pytest.mark.parametrize(("ziel", "zielwert", "groesse", "erwartet"), [
    # Beispiel A aus test_finance: P = 1 Mio., M = 50 000, EK 200 000, n = 9,07 %, k = 5,8 %, D = 890 700, B = 10 000
    ("cashflow_monat", 0, "kaufpreis", 815_673.58),          # = Kaufpreisempfehlung
    ("cashflow_monat", 0, "miete_ist", 64_575.75),           # (0 + 0 + 0,058 · 890 700) / 0,8
    ("cashflow_monat", 0, "zins", 0.0249085),                # 40 000 / 890 700 − 0,02
    ("cashflow_monat", 0, "eigenkapital", 401_044.83),       # 1 090 700 − 40 000 / 0,058
    ("bruttorendite", 0.06, "kaufpreis", 833_333.33),        # 50 000 / 0,06
    ("bruttorendite", 0.06, "miete_ist", 60_000.00),
    ("nettoanfangsrendite", 0.045, "kaufpreis", 814_971.02),  # 40 000 / (0,045 · 1,0907)
    ("nettoanfangsrendite", 0.045, "miete_ist", 61_351.88),   # 0,045 · 1 090 700 / 0,8
])
def test_rueckrechnung_handrechnung(ziel, zielwert, groesse, erwartet):
    l = loese(A, ziel, zielwert, groesse)
    assert l.status == "ok"
    assert l.wert == (pytest.approx(erwartet, abs=1e-6) if groesse == "zins" else approx(erwartet))
    assert _kennzahl(simulate(A, **{groesse: l.wert}), ziel) == pytest.approx(zielwert, abs=1e-6)


def test_rueckrechnung_sonderfaelle():
    assert loese(A, "cashflow_monat", 3_000, "zins").status == "nicht_erreichbar"  # Zins müsste negativ sein
    assert loese(A, "cashflow_monat", 3_500, "eigenkapital").status == "nicht_erreichbar"  # 42 000 > 40 000: reicht selbst ohne Darlehen nicht
    l = loese(A.mit(miete_ist=150_000), "cashflow_monat", 0, "eigenkapital")
    assert (l.status, l.wert) == ("immer_erreicht", 0.0)
    assert simulate(A.mit(miete_ist=150_000), eigenkapital=0.0).cashflow_monat >= 0
    assert loese(A.mit(miete_ist=None), "bruttorendite", 0.06, "kaufpreis").status == "miete_fehlt"
    assert loese(A.mit(miete_ist=None), "cashflow_monat", 0, "miete_ist").status == "ok"  # Miete selbst braucht keine Miete
    assert loese(A, "cashflow_monat", -10_000, "miete_ist").status == "immer_erreicht"
    with pytest.raises(ValueError):
        loese(A, "bruttorendite", 0.06, "zins")


def test_rueckrechnung_zufall_trifft_zielwert():
    rnd = random.Random(8)
    geloest = 0
    for _ in range(1500):
        a = A.mit(kaufpreis=rnd.uniform(2e5, 2e6), miete_ist=rnd.uniform(1e4, 1.5e5), wohnflaeche=rnd.uniform(150, 900),
                  zins=rnd.uniform(0, 0.07), tilgung=rnd.uniform(0, 0.04), sanierung_sofort=rnd.choice([0.0, rnd.uniform(0, 2e5)]),
                  eigenkapital=rnd.choice(["nebenkosten", rnd.uniform(0, 6e5)]), instandhaltung_eur_m2_jahr=rnd.uniform(0, 15),
                  bewirtschaftung_quote=rnd.uniform(0, 0.4), tilgung_einrechnen=rnd.random() < 0.7)
        ziel = rnd.choice(list(ZIEL_GROESSEN))
        groesse = rnd.choice(ZIEL_GROESSEN[ziel])
        zielwert = rnd.uniform(-500, 1500) if ziel == "cashflow_monat" else rnd.uniform(0.02, 0.09)
        l = loese(a, ziel, zielwert, groesse)
        if l.status == "ok":
            geloest += 1
            assert math.isclose(_kennzahl(simulate(a, **{groesse: l.wert}), ziel), zielwert, rel_tol=1e-9, abs_tol=1e-6)
        elif l.status == "immer_erreicht" and l.wert is not None:
            assert simulate(a, **{groesse: l.wert}).cashflow_monat >= zielwert - 1e-6
    assert geloest > 1200


# --------------------------------------------------------------------------- Objekt-Simulation am Bestand


@pytest.fixture
def bestand(welt):  # noqa: F811
    tc, config_dir, db, ids = welt
    conn = connect(db)
    yield tc, load_config(config_dir), conn, ids
    conn.close()


def test_ohne_aenderung_wie_detailansicht(bestand):
    _, cfg, conn, ids = bestand
    basis = osim.lade_basis(conn, cfg, ids["f1"])
    r = osim.rechne(basis, {})
    s = conn.execute("SELECT score, kaufpreisempfehlung, kpis_json FROM score WHERE listing_id = ?", (ids["f1"],)).fetchone()
    f = json.loads(s["kpis_json"])["finanzen"]
    assert r["simulation"] == r["basis"]
    assert r["simulation"]["score"] == s["score"]
    assert r["simulation"]["kaufpreisempfehlung"] == s["kaufpreisempfehlung"]
    for k in ("cashflow_monat", "bruttorendite", "darlehen", "nettoanfangsrendite"):
        assert r["simulation"][k] == f[k]


def test_formular_unveraendert_ergibt_keine_aenderung(bestand):
    _, cfg, conn, ids = bestand
    a = osim.lade_basis(conn, cfg, ids["f1"]).annahmen
    daten = {f"p_{p.name}": osim.eingabe_wert(p, getattr(a, p.name)) for p in osim.PARAMETER if p.art != "bool"}
    daten["p_tilgung_einrechnen"] = "1" if a.tilgung_einrechnen else ""
    daten["p_eigenkapital_art"] = "nebenkosten" if a.eigenkapital == "nebenkosten" else "betrag"
    daten["p_miete_m2"] = daten["p_miete_m2_vorher"] = str(osim.miete_m2(a.miete_ist, a.wohnflaeche) or "")
    assert osim.aus_formular(a, daten) == {}
    # Prozente kommen als Prozentzahl, die Miete auch als €/m² und Monat
    ae = osim.aus_formular(a, {**daten, "p_zins": "4,5", "p_miete_m2": "10"})
    assert ae["zins"] == pytest.approx(0.045)
    assert ae["miete_ist"] == pytest.approx(10 * 12 * a.wohnflaeche)
    with pytest.raises(osim.ObjektFehler):
        osim.aus_formular(a, {**daten, "p_kaufpreis": "-5"})


def test_rueckrechnung_und_score_am_angebot(bestand):
    _, cfg, conn, ids = bestand
    basis = osim.lade_basis(conn, cfg, ids["f1"])  # 900 000 €, Miete 54 000 € → 6 %
    ae, l = osim.loese_ziel(basis, {}, "bruttorendite", 0.07, "kaufpreis")
    assert l.status == "ok" and ae == {"kaufpreis": pytest.approx(54_000 / 0.07)}
    r = osim.rechne(basis, ae)
    assert r["simulation"]["bruttorendite"] == pytest.approx(0.07)
    assert r["simulation"]["score"] > r["basis"]["score"]
    # Kaufpreis so hoch, dass die Mindestrendite (4 %) verletzt ist → würde ausgeschlossen
    r = osim.rechne(basis, osim.normalisiere(basis.annahmen, {"kaufpreis": 1_500_000}))
    assert r["simulation"]["ausgeschlossen"].startswith("bruttorendite") and r["basis"]["ausgeschlossen"] is None
    # Ziel, das schon dem Ausgangswert entspricht, ändert nichts
    assert osim.loese_ziel(basis, {}, "bruttorendite", 0.06, "kaufpreis")[0] == {}
    with pytest.raises(osim.ObjektFehler):
        osim.loese_ziel(basis, {}, "nettoanfangsrendite", 0.05, "eigenkapital")


def test_szenarien_speichern_vergleichen_loeschen(bestand):
    _, cfg, conn, ids = bestand
    lid = ids["f1"]
    vorher = [tuple(r) for r in conn.execute("SELECT listing_id, profile_id, score, kaufpreisempfehlung FROM score ORDER BY listing_id")]
    basis = osim.lade_basis(conn, cfg, lid)
    s1 = osim.speichere_szenario(conn, basis, "Verhandlungsziel", {"kaufpreis": 800_000})
    s2 = osim.speichere_szenario(conn, basis, "Bank A", {"zins": 0.042, "tilgung": 0.015})
    with pytest.raises(osim.ObjektFehler):
        osim.speichere_szenario(conn, basis, "  ", {})
    liste = osim.szenarien(conn, lid, "mfh-a")
    assert {s["name"] for s in liste} == {"Verhandlungsziel", "Bank A"}
    gespeichert = osim.szenario(conn, s1, lid)
    assert gespeichert["annahmen"] == {"kaufpreis": 800_000.0}
    assert gespeichert["ergebnis"]["bruttorendite"] == pytest.approx(54_000 / 800_000)

    osim.speichere_szenario(conn, basis, "Verhandlungsziel 2", {"kaufpreis": 780_000}, szenario_id=s1)
    osim.umbenennen(conn, s2, lid, "Bank B")
    assert {s["name"] for s in osim.szenarien(conn, lid)} == {"Verhandlungsziel 2", "Bank B"}

    spalten = osim.vergleich(basis, [osim.szenario(conn, s1), osim.szenario(conn, s2)])
    assert [s["name"] for s in spalten] == ["Ausgangswert", "Verhandlungsziel 2", "Bank B"]
    assert spalten[1]["werte"]["bruttorendite"] == pytest.approx(54_000 / 780_000) and not spalten[1]["abweichungen"]
    with pytest.raises(osim.ObjektFehler):
        osim.vergleich(basis, [osim.szenario(conn, s1)] * 4)

    # neue Ausgangswerte (z. B. neue Extraktion) → Abweichung zum gespeicherten Stand wird angezeigt
    conn.execute("UPDATE extraction SET wert = '60000' WHERE listing_id = ? AND feld = 'jahresnettokaltmiete_ist'", (lid,))
    basis2 = osim.lade_basis(conn, cfg, lid)
    assert "Bruttorendite" in osim.vergleich(basis2, [osim.szenario(conn, s1)])[1]["abweichungen"]
    conn.rollback()

    osim.loesche_szenario(conn, s1, lid)
    with pytest.raises(osim.ObjektFehler):
        osim.loesche_szenario(conn, s2, lid + 1000)  # fremdes Angebot
    assert [s["name"] for s in osim.szenarien(conn, lid)] == ["Bank B"]
    nachher = [tuple(r) for r in conn.execute("SELECT listing_id, profile_id, score, kaufpreisempfehlung FROM score ORDER BY listing_id")]
    assert nachher == vorher  # Szenarien ändern keine Bewertung


# --------------------------------------------------------------------------- Oberfläche


def test_oberflaeche_simulation(bestand):
    tc, _, conn, ids = bestand
    csrf = _login(tc)
    lid = ids["f1"]
    seite = tc.get(f"/angebot/{lid}/simulation")
    assert seite.status_code == 200 and "Was-wäre-wenn" in seite.text and "Zielwert vorgeben" in seite.text
    assert "Simulieren" in tc.get(f"/angebot/{lid}").text
    assert tc.get("/angebot/9999/simulation").status_code == 404
    assert tc.post(f"/angebot/{lid}/simulation", data={"aktion": "rechnen"}).status_code == 403  # ohne CSRF

    r = tc.post(f"/angebot/{lid}/simulation", data={"csrf": csrf, "profil": "mfh-a", "p_kaufpreis": "1500000", "p_tilgung_einrechnen": "1",
                                                     "p_eigenkapital_art": "betrag", "aktion": "rechnen"})
    assert "würde ausgeschlossen" in r.text and 'class="geaendert"' in r.text
    r = tc.post(f"/angebot/{lid}/simulation", data={"csrf": csrf, "profil": "mfh-a", "p_tilgung_einrechnen": "1", "p_eigenkapital_art": "betrag",
                                                     "ziel_kombi": "bruttorendite:kaufpreis", "ziel_wert": "7", "aktion": "loesen"})
    assert "Kaufpreis berechnet" in r.text and "771.429 €" in r.text
    r = tc.post(f"/angebot/{lid}/simulation", data={"csrf": csrf, "profil": "mfh-a", "p_tilgung_einrechnen": "1", "p_eigenkapital_art": "betrag",
                                                     "p_kaufpreis": "800000", "name": "Verhandlungsziel", "aktion": "speichern"},
                follow_redirects=False)
    assert r.status_code == 303
    sid = conn.execute("SELECT id FROM scenario").fetchone()[0]
    assert r.headers["location"] == f"/angebot/{lid}/simulation?szenario={sid}"
    assert "Verhandlungsziel" in tc.get(f"/angebot/{lid}").text
    assert "Szenario „Verhandlungsziel“" in tc.get(r.headers["location"]).text
    v = tc.get(f"/angebot/{lid}/vergleich?profil=mfh-a&s={sid}")
    assert v.status_code == 200 and "Ausgangswert" in v.text and "800.000 €" in v.text
    tc.post(f"/angebot/{lid}/szenario/{sid}/loeschen", data={"csrf": csrf, "profil": "mfh-a"})
    assert conn.execute("SELECT COUNT(*) FROM scenario").fetchone()[0] == 0


def test_steuern_in_der_simulation(bestand):
    _, cfg, conn, ids = bestand
    basis = osim.lade_basis(conn, cfg, ids["f1"])
    a = basis.annahmen
    assert (a.grenzsteuersatz, a.gebaeudeanteil, a.afa_satz) == (0.42, 0.80, 0.02)  # Standard aus SteuernSettings
    daten = {"p_gebaeudeanteil": "70", "p_afa_satz": "2,5", "p_tilgung_einrechnen": "1" if a.tilgung_einrechnen else "",
             "p_eigenkapital_art": "betrag"}
    ae = osim.aus_formular(a, daten)
    assert ae == {"gebaeudeanteil": pytest.approx(0.70), "afa_satz": pytest.approx(0.025)}
    r = osim.rechne(basis, ae)
    s0, s1 = r["basis"], r["simulation"]
    assert s1["afa_jahr"] == pytest.approx(0.70 * s1["gesamtinvestition"] * 0.025)
    assert s1["steuer_jahr"] < s0["steuer_jahr"]  # mehr AfA → weniger Steuer
    assert s1["cashflow_monat"] == s0["cashflow_monat"] and s1["score"] == s0["score"]  # vor Steuern unverändert
    kpi = json.loads(conn.execute("SELECT kpis_json FROM score WHERE listing_id = ?", (ids["f1"],)).fetchone()[0])["alle_kpis"]
    assert kpi["cashflow_nach_steuern"]["wert"] == pytest.approx(s0["cashflow_nach_steuern_monat"])
