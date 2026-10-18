import json

from immo.config import load_config
from immo.sync import run_sync

from .conftest import PROFILE_B, FakeClient, make_listing


def count(conn, sql, *args):
    return conn.execute(sql, args).fetchone()[0]


def test_sync_is_idempotent(conn, config):
    client = FakeClient({"Job IS24": [make_listing(1), make_listing(2)], "Job KA": [make_listing(3, provider="kleinanzeigen")]})
    first = run_sync(conn, client, config)[0]
    second = run_sync(conn, client, config)[0]
    assert (first.neu, second.neu) == (3, 0)
    assert second.aktualisiert == 0
    assert count(conn, "SELECT COUNT(*) FROM listing") == 3
    assert count(conn, "SELECT COUNT(*) FROM listing_profile") == 3
    assert count(conn, "SELECT COUNT(*) FROM price_history") == 3
    assert count(conn, "SELECT COUNT(*) FROM run_log WHERE schritt = 'sync'") == 2
    # verschiedene Objekte → jedes bildet seine eigene Duplikatgruppe
    assert count(conn, "SELECT COUNT(*) FROM listing WHERE duplicate_group = id") == 3


def test_same_listing_with_tracking_params_is_not_duplicated(conn, config):
    a = make_listing(1, url="https://www.immobilienscout24.de/expose/1?referrer=x")
    client = FakeClient({"Job IS24": [a, make_listing(1)], "Job KA": []})
    run_sync(conn, client, config)
    assert count(conn, "SELECT COUNT(*) FROM listing") == 1


def test_fetch_filter_counts_but_does_not_store(conn, config):
    client = FakeClient({
        "Job IS24": [make_listing(1), make_listing(2, preis=2_000_000), make_listing(3, adresse="10115 Berlin"),
                     make_listing(4, titel="Zwangsversteigerung MFH")],
        "Job KA": [],
    })
    stats = run_sync(conn, client, config)[0]
    assert stats.neu == 1
    assert dict(stats.gefiltert) == {"preis": 1, "ort": 1, "stichwort": 1}
    assert count(conn, "SELECT COUNT(*) FROM listing") == 1


def test_price_change_and_description_change(conn, config):
    client = FakeClient({"Job IS24": [make_listing(1)], "Job KA": []})
    run_sync(conn, client, config)
    client.jobs["Job IS24"] = [make_listing(1, preis=750_000, beschreibung="Neuer Text")]
    stats = run_sync(conn, client, config)[0]
    assert (stats.preisaenderungen, stats.beschreibung_geaendert, stats.aktualisiert) == (1, 1, 1)
    prices = [r[0] for r in conn.execute("SELECT preis FROM price_history ORDER BY rowid")]
    assert prices == [800_000, 750_000]
    assert conn.execute("SELECT preis FROM listing").fetchone()[0] == 750_000


def test_price_rise_above_filter_keeps_known_listing(conn, config):
    client = FakeClient({"Job IS24": [make_listing(1)], "Job KA": []})
    run_sync(conn, client, config)
    client.jobs["Job IS24"] = [make_listing(1, preis=1_200_000)]
    run_sync(conn, client, config)
    assert count(conn, "SELECT COUNT(*) FROM listing WHERE preis = 1200000") == 1


def test_removed_and_reactivated(conn, config):
    client = FakeClient({"Job IS24": [make_listing(1), make_listing(2)], "Job KA": []})
    run_sync(conn, client, config)

    client.jobs["Job IS24"] = [make_listing(1)]
    assert run_sync(conn, client, config)[0].entfernt == 1
    assert conn.execute("SELECT status_portal FROM listing WHERE fredy_id = 'f2'").fetchone()[0] == "entfernt"

    client.jobs["Job IS24"] = [make_listing(1, is_active=False), make_listing(2)]
    stats = run_sync(conn, client, config)[0]
    assert (stats.entfernt, stats.reaktiviert) == (1, 1)


def test_failing_job_does_not_mark_listings_removed(conn, config):
    client = FakeClient({"Job IS24": [make_listing(1)], "Job KA": []})
    run_sync(conn, client, config)
    client.failing.add("Job IS24")
    stats = run_sync(conn, client, config)[0]
    assert stats.fehler and stats.entfernt == 0
    assert conn.execute("SELECT status_portal FROM listing").fetchone()[0] == "aktiv"
    log = conn.execute("SELECT fehler, zahlen_json FROM run_log ORDER BY id DESC").fetchone()
    assert "kaputt" in log[0] and json.loads(log[1])["fehler"]


def test_second_profile_applies_its_own_filter(conn, config_dir):
    (config_dir / "profiles" / "mfh-b.yaml").write_text(PROFILE_B, encoding="utf-8")
    config = load_config(config_dir)
    client = FakeClient({"Job IS24": [make_listing(1, preis=800_000), make_listing(2, preis=400_000)], "Job KA": []})
    stats = {s.profile_id: s for s in run_sync(conn, client, config)}
    assert stats["mfh-a"].neu == 2
    assert stats["mfh-b"].neu == 0 and stats["mfh-b"].gefiltert["preis"] == 1
    linked_b = [r[0] for r in conn.execute(
        "SELECT l.fredy_id FROM listing_profile lp JOIN listing l ON l.id = lp.listing_id WHERE profile_id = 'mfh-b'")]
    assert linked_b == ["f2"]
    assert count(conn, "SELECT COUNT(*) FROM listing") == 2


def test_listing_in_two_profiles_not_flagged_removed(conn, config_dir):
    (config_dir / "profiles" / "mfh-b.yaml").write_text(PROFILE_B.replace('job_prefix: "Job"', 'jobs: ["Job B"]'), encoding="utf-8")
    config = load_config(config_dir)
    shared = make_listing(1, preis=400_000)
    client = FakeClient({"Job IS24": [shared], "Job KA": [], "Job B": [shared]})
    run_sync(conn, client, config)
    client.jobs["Job IS24"] = []  # aus Profil A verschwunden, über Profil B weiter geliefert
    run_sync(conn, client, config)
    assert conn.execute("SELECT status_portal FROM listing").fetchone()[0] == "aktiv"
