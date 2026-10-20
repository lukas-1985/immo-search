"""Finanzrechnung gegen eine Handrechnung (5 Beispiele) und die Kerneigenschaft der Kaufpreisempfehlung."""

import random

import pytest

from immo.finance import Annahmen, simulate

BASIS = dict(
    kaufpreis=1_000_000, miete_ist=50_000, miete_qualitaet="extrahiert", wohnflaeche=400,
    grunderwerbsteuer=0.035, notar_grundbuch=0.02, makler=0.0357, sanierung_sofort=0, eigenkapital=200_000,
    zins=0.038, tilgung=0.02, bewirtschaftung_quote=0.20, instandhaltung_eur_m2_jahr=0,
    ziel_cashflow_monat=0, tilgung_einrechnen=True,
)
A = Annahmen(**BASIS)


def approx(x):
    return pytest.approx(x, abs=0.01)


def test_beispiel_a_neutraler_cashflow():
    e = simulate(A)
    assert e.darlehen == approx(890_700.00)
    assert e.zins_jahr == approx(33_846.60)
    assert e.tilgung_jahr == approx(17_814.00)
    assert e.cashflow_monat == approx(-971.72)
    assert e.bruttorendite == pytest.approx(0.05)
    assert e.faktor == pytest.approx(20.0)
    ke = e.kaufpreisempfehlung
    assert ke.status == "ok" and ke.preis == approx(815_673.58)
    assert ke.zins_minus == approx(875_325.00) and ke.zins_plus == approx(765_490.63)
    assert ke.preisabstand == pytest.approx((1_000_000 - 815_673.5788) / 1_000_000, abs=1e-8)
    assert ke.qualitaet == "extrahiert"


def test_beispiel_b_ziel_200_nur_zins():
    e = simulate(A, ziel_cashflow_monat=200, tilgung_einrechnen=False)
    assert e.cashflow_monat == approx(512.78)
    assert e.kaufpreisempfehlung.preis == approx(1_090_559.90)


def test_beispiel_c_sanierung_instandhaltung_provisionsfrei():
    e = simulate(A, kaufpreis=800_000, miete_ist=48_000, wohnflaeche=500, grunderwerbsteuer=0.065, makler=0.0,
                 sanierung_sofort=50_000, instandhaltung_eur_m2_jahr=10, eigenkapital=100_000)
    assert e.bewirtschaftung == approx(14_600.00)
    assert e.darlehen == approx(818_000.00)
    assert e.cashflow_monat == approx(-1_170.33)
    assert e.kaufpreisempfehlung.preis == approx(576_831.40)
    assert e.kaufpreisempfehlung.preisabstand == pytest.approx(0.278961, abs=1e-6)


def test_beispiel_d_ziel_nicht_erreichbar():
    e = simulate(A, miete_ist=20_000, wohnflaeche=1000, instandhaltung_eur_m2_jahr=15, ziel_cashflow_monat=100)
    ke = e.kaufpreisempfehlung
    assert ke.status == "nicht_erreichbar" and ke.preis is None and ke.text == "Ziel-Cashflow nicht erreichbar"


def test_beispiel_e_eigenkapital_deckt_alles():
    e = simulate(A, kaufpreis=400_000, miete_ist=30_000, eigenkapital=500_000)
    assert e.darlehen == 0.0  # kein negatives Darlehen
    assert e.cashflow_monat == approx(2_000.00)
    assert e.kaufpreisempfehlung.preis == approx(837_804.26)


def test_beispiel_f_eigenkapital_nur_nebenkosten():
    e = simulate(A, eigenkapital="nebenkosten")
    assert e.darlehen == approx(1_000_000.00)  # Kaufpreis voll finanziert
    assert e.cashflow_monat == approx(-1_500.00)  # 50 000 − 10 000 − 5,8 % · 1 000 000
    assert e.kaufpreisempfehlung.preis == approx(689_655.17)  # 40 000 / 0,058
    assert simulate(A, eigenkapital="nebenkosten", sanierung_sofort=50_000).darlehen == approx(1_050_000.00)


def test_sonderfaelle():
    assert simulate(A, miete_ist=None, miete_qualitaet=None).kaufpreisempfehlung.status == "miete_fehlt"
    assert simulate(A, zins=0.0, tilgung_einrechnen=False).kaufpreisempfehlung.status == "unbegrenzt"
    # Sanierung so hoch, dass selbst ein Kaufpreis von 0 das Ziel nicht trägt
    assert simulate(A, sanierung_sofort=2_000_000, eigenkapital=0).kaufpreisempfehlung.status == "nicht_erreichbar"
    with pytest.raises(ValueError, match="Unbekannte"):
        simulate(A, zinz=0.04)
    with pytest.raises(ValueError, match="Kaufpreis"):
        simulate(A, kaufpreis=0)


def test_beim_empfohlenen_preis_ist_cashflow_exakt_das_ziel():
    rnd = random.Random(42)
    for _ in range(500):
        a = A.mit(
            miete_ist=rnd.uniform(10_000, 200_000), wohnflaeche=rnd.uniform(100, 2000),
            grunderwerbsteuer=rnd.choice([0.035, 0.05, 0.065]), makler=rnd.choice([0.0, 0.0357, 0.0714]),
            sanierung_sofort=rnd.choice([0, 25_000, 100_000]), eigenkapital=rnd.choice([rnd.uniform(0, 300_000), "nebenkosten"]),
            zins=rnd.uniform(0.01, 0.07), tilgung=rnd.uniform(0.01, 0.04), bewirtschaftung_quote=rnd.uniform(0.1, 0.35),
            instandhaltung_eur_m2_jahr=rnd.choice([0, 8, 15]), ziel_cashflow_monat=rnd.choice([0, 100, 300]),
            tilgung_einrechnen=rnd.random() < 0.5,
        )
        ke = simulate(a).kaufpreisempfehlung
        if ke.status != "ok":
            continue
        assert simulate(a, kaufpreis=ke.preis).cashflow_monat == pytest.approx(a.ziel_cashflow_monat, abs=1e-6)
        assert ke.zins_plus < ke.preis < ke.zins_minus


def test_ohne_aenderungen_gleich_basis():
    assert simulate(A).as_dict() == simulate(A, **{}).as_dict()


# --------------------------------------------------------------------------- Steuern (vereinfacht, PLAN.md 5.7)

STEUER = dict(grenzsteuersatz=0.42, gebaeudeanteil=0.80, afa_satz=0.02)


def test_steuer_verlust_wird_ersparnis():
    # AfA = 0,8 · (1 000 000 + 90 700) · 0,02 = 17 451,20; Ergebnis = 50 000 − 10 000 − 33 846,60 − 17 451,20 = −11 297,80
    e = simulate(A, **STEUER)
    assert e.afa_jahr == approx(17_451.20)
    assert e.einkuenfte_jahr == approx(-11_297.80)
    assert e.steuer_jahr == approx(-4_745.08)  # Ersparnis
    assert e.cashflow_jahr == approx(-11_660.60)
    assert e.cashflow_nach_steuern_jahr == approx(-6_915.52)
    assert e.cashflow_nach_steuern_monat == approx(-576.29)
    # Score-relevante Werte und Kaufpreisempfehlung bleiben vor Steuern
    assert e.kaufpreisempfehlung.preis == approx(815_673.58)


def test_steuer_gewinn_und_tilgung_nicht_absetzbar():
    # Miete 80 000: B = 16 000, Ergebnis = 80 000 − 16 000 − 33 846,60 − 17 451,20 = 12 702,20 → Steuer 5 334,92
    e = simulate(A, miete_ist=80_000, **STEUER)
    assert e.steuer_jahr == approx(5_334.92)
    assert e.cashflow_nach_steuern_monat == approx((12_339.40 - 5_334.92) / 12)
    assert simulate(A, miete_ist=80_000, **{**STEUER, "tilgung": 0.04}).steuer_jahr == approx(5_334.92)
    # ohne Steuersatz: nach Steuern = vor Steuern; ohne Miete: keine Steuerrechnung
    e0 = simulate(A, **{**STEUER, "grenzsteuersatz": 0.0})
    assert e0.cashflow_nach_steuern_monat == pytest.approx(e0.cashflow_monat)
    assert simulate(A, miete_ist=None, **STEUER).cashflow_nach_steuern_monat is None
