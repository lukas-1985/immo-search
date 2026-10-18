import json
from pathlib import Path

import pytest

from immo.claude_io import objektart_by_listing, pending, save
from immo.extraction import MAX_VERSUCHE, belegstelle_found, field_values, load_schema, plausibility_error
from immo.parse_attrs import extract_rules, run_parse_attrs
from immo.sync import run_sync

from .conftest import FakeClient, make_listing

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "mfh_anzeigen.json").read_text(encoding="utf-8"))
SCHEMA = load_schema("mehrfamilienhaus")


@pytest.mark.parametrize("fx", FIXTURES, ids=lambda fx: f"anzeige{fx['nr']}")
def test_rules_on_fixtures(fx):
    found = {k: v["wert"] for k, v in extract_rules(fx["titel"], fx["beschreibung"], SCHEMA).items()}
    assert found == fx["regel"]


def test_rules_never_contradict_ground_truth():
    """Regelwerte haben Vorrang vor Claude – ein falscher Regelwert wäre ein echter Schaden."""
    for fx in FIXTURES:
        for feld, wert in {k: v["wert"] for k, v in extract_rules(fx["titel"], fx["beschreibung"], SCHEMA).items()}.items():
            if feld in fx["erwartet"]:
                assert wert == fx["erwartet"][feld], (fx["nr"], feld)


def test_rule_belegstellen_are_verbatim():
    for fx in FIXTURES:
        for feld, item in extract_rules(fx["titel"], fx["beschreibung"], SCHEMA).items():
            assert belegstelle_found(item["belegstelle"], fx["titel"], fx["beschreibung"]), (fx["nr"], feld)


def test_monthly_rule_has_rechenweg():
    item = extract_rules(None, "Monatliche Nettokaltmiete: 2.500 €", SCHEMA)["jahresnettokaltmiete_ist"]
    assert item["wert"] == 30000 and item["rechenweg"] == "2.500,00 € × 12 Monate"


def test_conflicting_values_give_no_rule_value():
    text = "Mieteinnahmen pro Jahr: 40.000 €\nJahresnettokaltmiete: 42.000 €"
    assert "jahresnettokaltmiete_ist" not in extract_rules(None, text, SCHEMA)


def test_belegstelle_tolerates_whitespace_quotes_and_ellipsis():
    text = "Das Haus „Lindenhof“ hat\n6   Wohnungen. Im Keller ist es feucht."
    assert belegstelle_found('Das Haus "Lindenhof" hat 6 Wohnungen', text)
    assert belegstelle_found("hat 6 Wohnungen … Keller ist es feucht", text)
    assert not belegstelle_found("hat 8 Wohnungen", text)
    assert not belegstelle_found(" … ", text)


def test_plausibility():
    assert "Monats" in plausibility_error("jahresnettokaltmiete_ist", 3150, {}, 690000)
    assert plausibility_error("jahresnettokaltmiete_ist", 37800, {}, 690000) is None
    assert plausibility_error("leerstand_einheiten", 5, {"wohneinheiten": {"wert": 4}}, None)


# --------------------------------------------------------------------------- pending / save


@pytest.fixture
def seeded(conn, config):
    listings = [
        make_listing(fx["nr"], provider=fx["provider"], titel=fx["titel"], adresse=fx["adresse"], preis=fx["preis"],
                     flaeche=fx["flaeche"], baujahr=fx["baujahr"], beschreibung=fx["beschreibung"],
                     url=f"https://example.test/{fx['nr']}")
        for fx in FIXTURES
    ]
    # alle Anzeigen sollen den fetch_filter des Testprofils passieren
    for l in listings:
        l.plz, l.ort, l.preis = "80331", "München", min(l.preis, 990_000)
    client = FakeClient({"Job IS24": listings, "Job KA": []})
    run_sync(conn, client, config)
    run_parse_attrs(conn, objektart_by_listing(conn, config))
    return conn, config, client


def _id(conn, nr: int) -> int:
    return conn.execute("SELECT id FROM listing WHERE fredy_id = ?", (f"f{nr}",)).fetchone()[0]


def _result(conn, nr: int, felder: dict) -> dict:
    lid = _id(conn, nr)
    h = conn.execute("SELECT beschreibung_hash FROM listing WHERE id = ?", (lid,)).fetchone()[0]
    return {"listing_id": lid, "beschreibung_hash": h, "felder": felder}


def test_pending_lists_unextracted_and_known_fields(seeded):
    conn, config, _ = seeded
    out = pending(conn, config, limit=5)
    assert out["anzahl"] == 5 and out["offen_gesamt"] == 12
    first = out["angebote"][0]
    assert first["bekannt"]["wohneinheiten"] == 6
    assert "wohneinheiten" not in first["gesucht"] and "risiken" in first["gesucht"]


def test_save_accepts_valid_and_rejects_invalid(seeded):
    conn, config, _ = seeded
    ok = _result(conn, 2, {
        "jahresnettokaltmiete_ist": {"wert": 37800, "konfidenz": "mittel", "rechenweg": "3.150 € × 12",
                                     "belegstelle": "eine monatliche Nettokaltmiete von insgesamt 3.150 € erzielen"},
        "wohneinheiten": {"wert": 4, "konfidenz": "hoch", "belegstelle": "verfügt über 4 Wohnungen"},
        "heizungsart": {"wert": "Öl", "konfidenz": "hoch", "belegstelle": "Ölheizung von 1998"},
        "risiken": {"wert": ["erfundenes Risiko"], "konfidenz": "hoch", "belegstelle": "Schimmel im Bad"},
    })
    bad = _result(conn, 3, {"wohneinheiten": {"wert": "acht", "konfidenz": "hoch", "belegstelle": "8 Wohneinheiten"}})
    report = save(conn, config, {"ergebnisse": [ok, bad]})

    accepted = report.angenommen[ok["listing_id"]]
    assert sorted(accepted["gespeichert"]) == ["heizungsart", "jahresnettokaltmiete_ist"]
    assert accepted["uebersprungen"] == {"wohneinheiten": "bereits aus Quelle 'regel'"}
    assert "risiken" in accepted["feld_abgelehnt"]
    assert bad["listing_id"] in report.abgelehnt

    values = field_values(conn, ok["listing_id"])
    assert values["jahresnettokaltmiete_ist"] == {"wert": 37800, "rechenweg": "3.150 € × 12", "quelle": "claude",
                                                   "konfidenz": "mittel",
                                                   "belegstelle": "eine monatliche Nettokaltmiete von insgesamt 3.150 € erzielen"}
    assert values["wohneinheiten"]["quelle"] == "regel"

    left = {a["listing_id"] for a in pending(conn, config, limit=50)["angebote"]}
    assert ok["listing_id"] not in left and bad["listing_id"] in left


def test_rejected_listing_is_retried_limited_times(seeded):
    conn, config, _ = seeded
    bad = _result(conn, 5, {"wohneinheiten": {"wert": 5}})  # konfidenz/belegstelle fehlen
    for _ in range(MAX_VERSUCHE):
        assert bad["listing_id"] in {a["listing_id"] for a in pending(conn, config, limit=50)["angebote"]}
        save(conn, config, {"ergebnisse": [bad]})
    assert bad["listing_id"] not in {a["listing_id"] for a in pending(conn, config, limit=50)["angebote"]}
    # ausdrücklich angefordert geht immer
    assert pending(conn, config, listing_id=bad["listing_id"], reextract=True)["anzahl"] == 1


def test_changed_description_triggers_reextraction(seeded):
    conn, config, client = seeded
    r = _result(conn, 5, {"wohneinheiten": {"wert": 5, "konfidenz": "hoch", "belegstelle": "5-Parteienhaus"}})
    save(conn, config, {"ergebnisse": [r]})
    assert r["listing_id"] not in {a["listing_id"] for a in pending(conn, config, limit=50)["angebote"]}

    stale = dict(r)
    listing = next(l for l in client.jobs["Job IS24"] if l.fredy_id == "f5")
    listing.beschreibung += " Neu: Jahresmiete 48.000 €."
    run_sync(conn, client, config)
    assert r["listing_id"] in {a["listing_id"] for a in pending(conn, config, limit=50)["angebote"]}
    # Ein Ergebnis zur alten Fassung wird abgelehnt
    assert "geändert" in save(conn, config, {"ergebnisse": [stale]}).abgelehnt[r["listing_id"]][0]


def test_reextract_replaces_previous_claude_values(seeded):
    conn, config, _ = seeded
    first = _result(conn, 8, {
        "jahresnettokaltmiete_ist": {"wert": 44500, "konfidenz": "hoch", "belegstelle": "netto kalt 44.500 € im Jahr"},
        "heizungsart": {"wert": "Gas-Etagenheizung", "konfidenz": "hoch", "belegstelle": "Gas-Etagenheizungen"},
    })
    save(conn, config, {"ergebnisse": [first]})
    second = _result(conn, 8, {
        "jahresnettokaltmiete_ist": {"wert": 44500, "konfidenz": "hoch", "belegstelle": "netto kalt 44.500 € im Jahr"},
    })
    save(conn, config, {"ergebnisse": [second]})
    assert "heizungsart" not in field_values(conn, first["listing_id"])


def test_save_rejects_unknown_listing_and_bad_payload(seeded):
    conn, config, _ = seeded
    assert save(conn, config, {"ergebnisse": [{"listing_id": 9999}]}).abgelehnt == {9999: ["unbekanntes oder nicht aktives Angebot"]}
    with pytest.raises(ValueError):
        save(conn, config, [{"listing_id": 1}])
