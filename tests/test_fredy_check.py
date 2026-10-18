import httpx

from immo.config import FredySettings
from immo.fredy_check import check
from immo.fredy_client import FredyApiClient

JOBS = [{"id": "j1", "name": "Job IS24", "enabled": True}, {"id": "j2", "name": "Job KA", "enabled": True},
        {"id": "j3", "name": "Job Sonstiges", "enabled": False}]

ROWS = {
    "j1": [
        {"id": "a", "provider": "immoscout", "link": "https://is24.de/1", "price": 800000, "size": 400, "title": "MFH",
         "address": "Weg 1, 80331 München", "description": "Mieteinnahmen pro Jahr: 48.000 €\n" + "x" * 400,
         "created_at": 1760000000000, "is_active": 1, "market_median_sqm": 5200, "similar_listings": None},
        {"id": "b", "provider": "immoscout", "link": "https://is24.de/2", "price": 2000000, "size": 900, "title": "Groß",
         "address": "10115 Berlin", "description": "kurz", "created_at": 1760000100000, "is_active": 1},
    ],
    "j2": [
        {"id": "c", "provider": "kleinanzeigen", "link": "https://ka.de/1", "price": 810000, "size": 405, "title": "MFH privat",
         "address": "80331 München", "description": "Text …", "created_at": 1760000200000, "is_active": 0},
        {"id": None, "provider": "kleinanzeigen", "link": None},
    ],
    "j3": [],
}


def _client():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/login":
            return httpx.Response(200)
        if request.url.path == "/api/jobs":
            return httpx.Response(200, json=JOBS)
        return httpx.Response(200, json={"result": ROWS[request.url.params["jobIdFilter"]]})

    return FredyApiClient(FredySettings(base_url="http://fredy.test"), "u", "p", transport=httpx.MockTransport(handler))


def test_check_reports_open_points(config):
    bericht, roh = check(_client(), config, stichprobe=1)

    assert bericht["profile"]["mfh-a"]["jobs"] == ["Job IS24", "Job KA"]
    assert [j["aktiv"] for j in bericht["jobs"]] == [True, True, False]

    is24 = bericht["je_job"]["Job IS24"]
    assert is24["anzahl"] == 2 and is24["portale"] == {"immoscout": 2}
    assert is24["abdeckung"]["plz"] == 1.0 and is24["abdeckung"]["koordinaten"] == 0.0
    assert is24["nicht_gelesen"] == ["market_median_sqm", "similar_listings"]
    assert is24["duplikat_felder"] == ["similar_listings"]
    assert is24["regel_findet_ist_miete"] == 0.5
    assert is24["beschreibung"]["anteil_unter_300_zeichen"] == 0.5

    ka = bericht["je_job"]["Job KA"]
    assert ka["abbildungsfehler"] == 1 and ka["aktiv"] == 0
    assert ka["beschreibung"]["enden_mit_auslassung"] == 1

    # Testprofil: PLZ 80…/Freising, Preis ≤ 1 Mio. → Berlin fällt raus
    assert bericht["profile"]["mfh-a"]["fetch_filter"] == {"passt": 2, "preis": 1}
    assert len(bericht["duplikat_kandidaten"]) == 1
    assert len(roh["listings"]["Job IS24"]) == 1


def test_check_suggests_similar_job_names(config):
    global JOBS
    JOBS[0]["name"] = "Job IS-24"
    try:
        bericht, _ = check(_client(), config)
    finally:
        JOBS[0]["name"] = "Job IS24"
    fehlend = bericht["profile"]["mfh-a"]["fehlend"]
    assert fehlend == [{"name": "Job IS24", "aehnlich": ["Job IS-24"]}]
