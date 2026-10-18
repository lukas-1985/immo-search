import json

import pytest

from immo.config import ConfigError, Normalize, Profile, load_config
from immo.kpis import normalisiere
from immo.scoring import FormelFehler, bewerte, pruefe_profil, ranking, run_score, werte_formel

from .conftest import FakeClient, make_listing

SETTINGS = """
grunderwerbsteuer: { BY: 0.035 }
finance_defaults: { zins: 0.038, tilgung: 0.02, notar_grundbuch: 0.02, makler_default: 0.0357, bewirtschaftung_quote: 0.20 }
"""

PROFIL = """
id: mfh-a
name: "MFH A"
objektart: mehrfamilienhaus
fredy: { jobs: ["Job IS24", "Job KA"] }
hard_filter:
  - { field: erbpacht,      op: "==", value: false, on_missing: keep }
  - { field: wohneinheiten, op: ">=", value: 3,     on_missing: keep }
  - { field: bruttorendite, op: ">=", value: 0.04,  on_missing: keep }
scoring:
  kpis:
    bruttorendite: { weight: 1.0, normalize: { type: linear, min: 0.04, max: 0.08 }, on_missing: estimate }
finance: { bundesland: BY, eigenkapital: 200000 }
"""


@pytest.fixture
def cfg(config_dir):
    (config_dir / "settings.yaml").write_text(SETTINGS, encoding="utf-8")
    (config_dir / "profiles" / "mfh-a.yaml").write_text(PROFIL, encoding="utf-8")
    return load_config(config_dir)


def feld(wert, quelle="claude"):
    return {"wert": wert, "quelle": quelle, "konfidenz": "hoch", "belegstelle": "x"}


LISTING = {"id": 1, "preis": 1_000_000, "flaeche": 400, "plz": "80331", "ort": "München", "provider": "immoscout"}


def test_normalisierung():
    n = Normalize(min=0.04, max=0.08)
    assert [normalisiere(v, n) for v in (0.03, 0.04, 0.06, 0.08, 0.1)] == pytest.approx([0, 0, 50, 100, 100])
    assert normalisiere(16, Normalize(min=25, max=12)) == pytest.approx(69.2307, abs=1e-3)  # Faktor: niedriger ist besser


def test_bewertung_mit_handrechnung(cfg):
    b = bewerte(cfg, cfg.profiles["mfh-a"], LISTING, {"jahresnettokaltmiete_ist": feld(60_000), "wohneinheiten": feld(6, "regel")})
    # Bruttorendite 6 % → 50 Punkte
    assert b.score == pytest.approx(50.0) and not b.ausgeschlossen
    # P* = ((60.000 − 12.000) / 0,058 + 200.000) / 1,0907 (identisch zu Beispiel A in test_finance, nur andere Miete)
    assert b.kaufpreisempfehlung == pytest.approx(((48_000 / 0.058) + 200_000) / 1.0907, abs=0.01)
    assert b.details["kpis"]["bruttorendite"] == {"wert": 0.06, "qualitaet": "extrahiert", "gewicht": 1.0,
                                                  "on_missing": "estimate", "punkte": pytest.approx(50.0), "verwendet": True}
    assert b.details["unvollstaendig"] == ["erbpacht"]  # Ausschlusskriterium ohne Wert → behalten, markiert
    assert b.details["finanzen"]["annahmen"]["makler_quelle"] == "default"


def test_provision_aus_anzeige_wird_verwendet(cfg):
    b = bewerte(cfg, cfg.profiles["mfh-a"], LISTING, {"jahresnettokaltmiete_ist": feld(60_000), "provision": feld(0.0)})
    assert b.details["finanzen"]["annahmen"]["makler"] == 0.0
    assert b.kaufpreisempfehlung == pytest.approx(((48_000 / 0.058) + 200_000) / 1.055, abs=0.01)


@pytest.mark.parametrize("felder, grund", [
    ({"erbpacht": feld(True)}, "erbpacht == False verletzt"),
    ({"wohneinheiten": feld(2)}, "wohneinheiten >= 3 verletzt"),
    ({"jahresnettokaltmiete_ist": feld(30_000)}, "bruttorendite >= 0.04 verletzt"),
])
def test_ausschlusskriterien(cfg, felder, grund):
    b = bewerte(cfg, cfg.profiles["mfh-a"], LISTING, felder)
    assert b.ausgeschlossen and b.ausschlussgrund.startswith(grund)


def test_on_missing_drop(cfg):
    p = cfg.profiles["mfh-a"].model_copy(deep=True)
    p.hard_filter[0].on_missing = "drop"
    b = bewerte(cfg, p, LISTING, {"jahresnettokaltmiete_ist": feld(60_000)})
    assert b.ausgeschlossen and b.ausschlussgrund == "erbpacht fehlt"


def test_fehlende_miete_und_schaetzung(cfg):
    p = cfg.profiles["mfh-a"]
    ohne = bewerte(cfg, p, LISTING, {})
    assert ohne.score == 0.0 and ohne.kaufpreisempfehlung is None and "Miete fehlt" in ohne.details["hinweise"]
    assert "bruttorendite" in ohne.details["unvollstaendig"]

    p = p.model_copy(deep=True)
    p.finance.miete_schaetzung_eur_m2 = 12.5  # 12,50 € × 400 m² × 12 = 60.000 €
    geschaetzt = bewerte(cfg, p, LISTING, {})
    assert geschaetzt.score == pytest.approx(50.0)
    assert geschaetzt.details["kpis"]["bruttorendite"]["qualitaet"] == "geschätzt"
    assert "Kaufpreisempfehlung beruht auf geschätzter Miete" in geschaetzt.details["hinweise"]

    p.scoring.kpis["bruttorendite"].on_missing = "zero"
    assert bewerte(cfg, p, LISTING, {}).score == 0.0
    p.scoring.kpis["bruttorendite"].on_missing = "exclude"
    assert bewerte(cfg, p, LISTING, {}).score is None


def test_gewichtete_summe_und_formel(cfg):
    p = cfg.profiles["mfh-a"].model_copy(deep=True)
    p.scoring.kpis["faktor"] = p.scoring.kpis["bruttorendite"].model_copy(update={"weight": 3.0, "normalize": Normalize(min=25, max=12)})
    b = bewerte(cfg, p, LISTING, {"jahresnettokaltmiete_ist": feld(60_000)})
    # Bruttorendite 50 Pkt (Gewicht 1), Faktor 16,67 → (25 − 16,67) / 13 × 100 = 64,10 Pkt (Gewicht 3)
    assert b.score == pytest.approx((50 + 3 * (25 - 1_000_000 / 60_000) / 13 * 100) / 4, abs=1e-3)

    p.scoring.formula = "0.5 * bruttorendite_n + 0.5 * min(faktor_n, 60)"
    assert bewerte(cfg, p, LISTING, {"jahresnettokaltmiete_ist": feld(60_000)}).score == pytest.approx(55.0)


def test_formel_ist_sicher():
    assert werte_formel("2 * a + max(b, 1) - -1", {"a": 3, "b": 0.5}) == 8
    for boese in ("__import__('os')", "a.b", "[1, 2]", "a if b else c", "'x'", "open('f')", "a ** 2"):
        with pytest.raises(FormelFehler):
            werte_formel(boese, {"a": 1, "b": 1, "c": 1})


def test_profilpruefung(cfg):
    p = cfg.profiles["mfh-a"]
    pruefe_profil(p)
    bad = Profile.model_validate({**p.model_dump(), "hard_filter": [{"field": "erbpach", "op": "==", "value": False}],
                                  "scoring": {"kpis": {"rendite": p.scoring.kpis["bruttorendite"].model_dump()}, "formula": "foo_n + 1"}})
    with pytest.raises(ConfigError) as exc:
        pruefe_profil(bad)
    msg = str(exc.value)
    assert "erbpach" in msg and "rendite" in msg and "foo_n" in msg


def test_fehlende_finanzannahme(config_dir):
    cfg = load_config(config_dir)  # Test-settings ohne finance_defaults
    with pytest.raises(ConfigError, match="zins"):
        bewerte(cfg, cfg.profiles["mfh-a"], LISTING, {})


def test_run_score_und_ranking(conn, cfg):
    client = FakeClient({"Job IS24": [make_listing(1, preis=900_000), make_listing(2, preis=700_000), make_listing(3)], "Job KA": []})
    from immo.sync import run_sync

    run_sync(conn, client, cfg)
    ids = {r[1]: r[0] for r in conn.execute("SELECT id, fredy_id FROM listing")}
    for fid, miete, extra in (("f1", 54_000, {}), ("f2", 49_000, {}), ("f3", 60_000, {"erbpacht": True})):
        for name, wert in {"jahresnettokaltmiete_ist": miete, **extra}.items():
            conn.execute("INSERT INTO extraction VALUES (?, ?, ?, 'claude', 'hoch', 'x', 1, '2026-10-18')", (ids[fid], name, json.dumps(wert)))
    conn.commit()

    stats = run_score(conn, cfg)[0]
    assert (stats.bewertet, stats.ausgeschlossen) == (3, 1)
    top = ranking(conn, cfg, "mfh-a")
    assert [r["id"] for r in top] == [ids["f2"], ids["f1"]]  # 7,0 % vor 6,0 %
    assert len(ranking(conn, cfg, "mfh-a", ausgeschlossene=True)) == 3

    # Erneute Bewertung ist deterministisch
    vorher = conn.execute("SELECT listing_id, score, kpis_json, config_hash FROM score ORDER BY listing_id").fetchall()
    run_score(conn, cfg)
    nachher = conn.execute("SELECT listing_id, score, kpis_json, config_hash FROM score ORDER BY listing_id").fetchall()
    assert [tuple(r) for r in vorher] == [tuple(r) for r in nachher]

    # verworfene Angebote verschwinden aus dem Ranking
    conn.execute("INSERT INTO workflow VALUES (?, 'verworfen', '2026-10-18', 'ui')", (ids["f2"],))
    assert [r["id"] for r in ranking(conn, cfg, "mfh-a")] == [ids["f1"]]
