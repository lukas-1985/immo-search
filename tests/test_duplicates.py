from immo.duplicates import gruppiere_duplikate, ist_duplikat
from immo.scoring import ranking
from immo.sync import run_sync

from .conftest import FakeClient, make_listing

TITEL = "Topgepflegtes 4- bis 5-Familienhaus in Innenstadtlage von Kaiserslautern"


def _row(**kw):
    d = dict(provider="immoscout", plz="67655", titel=TITEL, preis=790_000.0, flaeche=302.0)
    d.update(kw)
    return d


def test_gleiches_objekt_auf_zwei_portalen():
    assert ist_duplikat(_row(), _row(provider="kleinanzeigen"))
    # kleine Abweichungen: Satzzeichen, Preis ± 5 %, Fläche ± 2 %
    assert ist_duplikat(_row(), _row(provider="kleinanzeigen", titel=TITEL.upper() + "!", preis=770_000.0, flaeche=300.0))


def test_keine_duplikate():
    ka = dict(provider="kleinanzeigen")
    assert not ist_duplikat(_row(), _row())  # gleiches Portal
    assert not ist_duplikat(_row(), _row(**ka, plz="67657"))
    assert not ist_duplikat(_row(), _row(**ka, preis=850_000.0))
    assert not ist_duplikat(_row(), _row(**ka, flaeche=320.0))
    assert not ist_duplikat(_row(plz=None), _row(**ka, plz=None))
    # echtes Gegenbeispiel KL, 18.10.2026: gleiche PLZ, Fläche/Preis nah, verschiedene Häuser
    assert not ist_duplikat(
        _row(plz="67659", titel="Vermietetes Mehrfamilienhaus mit drei Wohneinheiten im Tal von Morlautern", preis=395_000.0, flaeche=224.0),
        _row(**ka, plz="67659", titel="Kaiserslautern – Saniertes MFH mit 4 Einheiten | Starke Kapitalanlage", preis=410_000.0, flaeche=226.0),
    )


def _ka(n: int, **kw):
    return make_listing(n, provider="kleinanzeigen", url=f"https://www.kleinanzeigen.de/s-anzeige/{n}", **kw)


def test_sync_gruppiert_und_ranking_zeigt_objekt_einmal(conn, config):
    is24 = make_listing(1, titel=TITEL, preis=790_000, flaeche=302)
    anderes = make_listing(2, titel="Anderes Haus")
    client = FakeClient({"Job IS24": [is24, anderes], "Job KA": [_ka(3, titel=TITEL, preis=790_000, flaeche=302)]})
    stats = run_sync(conn, client, config)[0]
    gruppe = {r["titel"] + r["provider"]: r["duplicate_group"] for r in conn.execute("SELECT * FROM listing")}
    assert stats.duplikate == 2
    assert gruppe[TITEL + "immoscout"] == gruppe[TITEL + "kleinanzeigen"] != gruppe["Anderes Hausimmoscout"]

    for (lid,) in conn.execute("SELECT id FROM listing").fetchall():
        conn.execute("""INSERT INTO score (listing_id, profile_id, score, kpis_json, hard_filter_result, config_hash, scored_at)
                        VALUES (?, 'mfh-a', ?, '{}', 'bestanden', 'x', '2026-10-18')""", (lid, 50 + lid))
    titel = [r["titel"] for r in ranking(conn, config, "mfh-a")]
    assert sorted(titel) == ["Anderes Haus", TITEL]
    assert len(ranking(conn, config, "mfh-a", limit=1)) == 1


def test_workflow_status_geht_beim_zusammenlegen_nicht_verloren(conn, config):
    # KA zuerst (kleinere ID); IS24 zunächst teurer → kein Duplikat, eigener Status
    ka = _ka(1, titel=TITEL, preis=790_000, flaeche=302)
    run_sync(conn, FakeClient({"Job IS24": [make_listing(2, titel=TITEL, preis=900_000, flaeche=302)], "Job KA": [ka]}), config)
    ka_id, is24_id = (conn.execute("SELECT id FROM listing WHERE provider = ?", (p,)).fetchone()[0] for p in ("kleinanzeigen", "immoscout"))
    assert gruppiere_duplikate(conn) == 0
    conn.execute("INSERT INTO workflow (duplicate_group, status, updated_at, updated_by) VALUES (?, 'besichtigt', '2026-10-18', 'ui')", (is24_id,))
    conn.commit()

    # Preissenkung auf IS24 → jetzt dasselbe Objekt; Gruppe = kleinere ID, Status wandert mit
    run_sync(conn, FakeClient({"Job IS24": [make_listing(2, titel=TITEL, preis=790_000, flaeche=302)], "Job KA": [ka]}), config)
    gruppe = conn.execute("SELECT duplicate_group FROM listing WHERE id = ?", (is24_id,)).fetchone()[0]
    assert gruppe == min(ka_id, is24_id)
    assert conn.execute("SELECT status FROM workflow WHERE duplicate_group = ?", (gruppe,)).fetchone()[0] == "besichtigt"
    assert conn.execute("SELECT COUNT(*) FROM workflow").fetchone()[0] == 1
