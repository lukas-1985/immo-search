import pytest

from immo import config_edit as ce
from immo.db import connect

PROFIL = """id: mfh-a
name: "MFH A"   # Name
objektart: mehrfamilienhaus
fredy: { jobs: ["Job IS24"] }
hard_filter:
  - { field: erbpacht,      op: "==", value: false, on_missing: keep }
  - { field: bruttorendite, op: ">=", value: 0.04,  on_missing: keep }   # Mindestrendite
scoring:
  kpis:
    bruttorendite: { weight: 1.0, normalize: { type: linear, min: 0.04, max: 0.08 }, on_missing: estimate }
finance:
  bundesland: BY
  eigenkapital: nebenkosten        # EK = Nebenkosten

kaufpreisempfehlung:
  ziel_cashflow_monat: 0
"""

SETTINGS = """grunderwerbsteuer: { BY: 0.035 }
finance_defaults: { zins: 0.038, tilgung: 0.02, notar_grundbuch: 0.02, makler_default: 0.0357, bewirtschaftung_quote: 0.20 }
"""


@pytest.fixture
def cdir(tmp_path):
    d = tmp_path / "config"
    (d / "profiles").mkdir(parents=True)
    (d / "settings.yaml").write_text(SETTINGS, encoding="utf-8")
    (d / "profiles" / "mfh-a.yaml").write_text(PROFIL, encoding="utf-8")
    return d


def test_setze_werte_aendert_nur_den_wert():
    neu = ce.setze_werte(PROFIL, {("hard_filter", 1, "value"): 0.05, ("finance", "eigenkapital"): 50000,
                                  ("scoring", "kpis", "bruttorendite", "normalize", "max"): 0.09, ("name",): "MFH B"})
    alt_z, neu_z = PROFIL.splitlines(), neu.splitlines()
    geaendert = [(a, b) for a, b in zip(alt_z, neu_z, strict=True) if a != b]
    assert geaendert == [
        ('name: "MFH A"   # Name', "name: MFH B   # Name"),
        ('  - { field: bruttorendite, op: ">=", value: 0.04,  on_missing: keep }   # Mindestrendite',
         '  - { field: bruttorendite, op: ">=", value: 0.05,  on_missing: keep }   # Mindestrendite'),
        ("    bruttorendite: { weight: 1.0, normalize: { type: linear, min: 0.04, max: 0.08 }, on_missing: estimate }",
         "    bruttorendite: { weight: 1.0, normalize: { type: linear, min: 0.04, max: 0.09 }, on_missing: estimate }"),
        ("  eigenkapital: nebenkosten        # EK = Nebenkosten", "  eigenkapital: 50000        # EK = Nebenkosten"),
    ]


def test_setze_werte_neuer_schluessel_im_block():
    neu = ce.setze_werte(PROFIL, {("finance", "zins"): 0.03})
    assert "  eigenkapital: nebenkosten        # EK = Nebenkosten\n  zins: 0.03\n\nkaufpreisempfehlung:" in neu


def test_pfade_und_backups(cdir, tmp_path):
    for schlecht in ("../.env", "profiles/../x.yaml", "profiles/A.yaml", "sonst.yaml"):
        with pytest.raises(ce.EditFehler):
            ce.pruefe_pfad(schlecht)
    conn = connect(tmp_path / "t.db")
    r = ce.speichern(conn, cdir, "profiles/mfh-a.yaml", PROFIL.replace("value: 0.04", "value: 0.05"))
    assert r["geaendert"] and "+  - { field: bruttorendite" in r["diff"]
    assert ce.speichern(conn, cdir, "profiles/mfh-a.yaml", (cdir / "profiles/mfh-a.yaml").read_text(encoding="utf-8"))["geaendert"] is False
    (b,) = ce.backups(cdir)
    rel, text = ce.backup_lesen(cdir, b["name"])
    assert rel == "profiles/mfh-a.yaml" and text == PROFIL
    with pytest.raises(ce.EditFehler):
        ce.backup_lesen(cdir, "../settings.yaml")
    # ungültig → nichts geschrieben
    with pytest.raises(ce.EditFehler, match="bundesland|Bundesland"):
        ce.speichern(conn, cdir, "profiles/mfh-a.yaml", PROFIL.replace("bundesland: BY", "bundesland: XX"))
    assert conn.execute("SELECT COUNT(*) FROM config_change").fetchone()[0] == 1


def test_profil_kopieren_und_aktivieren(cdir, tmp_path):
    conn = connect(tmp_path / "t.db")
    ce.profil_kopieren(conn, cdir, "mfh-a", "mfh-b", "Zweites Profil")
    text = (cdir / "profiles" / "mfh-b.yaml").read_text(encoding="utf-8")
    assert text.startswith("id: mfh-b\nname: Zweites Profil   # Name\n") and "active: false" in text
    ce.profil_aktiv(conn, cdir, "mfh-b", True)
    assert "active: true" in (cdir / "profiles" / "mfh-b.yaml").read_text(encoding="utf-8")
    with pytest.raises(ce.EditFehler, match="gibt es schon"):
        ce.profil_kopieren(conn, cdir, "mfh-a", "mfh-b")
