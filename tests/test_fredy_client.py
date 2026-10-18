import json
import sqlite3

import httpx
import pytest

from immo.config import FredySettings, Profile, ConfigError
from immo.fredy_client import FredyApiClient, FredyError, FredySqliteClient, resolve_jobs
from immo.models import FredyJob


def _row(n: int) -> dict:
    return {"id": f"x{n}", "provider": "immoscout", "link": f"https://is24.de/expose/{n}", "price": 100_000 + n, "job_id": "j1"}


def test_api_client_logs_in_and_pages():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/login":
            assert json.loads(request.content) == {"username": "u", "password": "p"}
            return httpx.Response(200, headers={"set-cookie": "fredy-session=abc; Path=/"})
        assert request.headers.get("cookie") == "fredy-session=abc"
        if request.url.path == "/api/jobs":
            return httpx.Response(200, json=[{"id": "j1", "name": "Job 1"}])
        page = int(request.url.params["page"])
        assert request.url.params["jobIdFilter"] == "j1"
        rows = [_row(n) for n in range((page - 1) * 2, min(page * 2, 5))]
        return httpx.Response(200, json={"totalNumber": 5, "page": page, "result": rows})

    client = FredyApiClient(FredySettings(base_url="http://fredy.test", page_size=2), "u", "p", transport=httpx.MockTransport(handler))
    jobs = client.list_jobs()
    listings = list(client.iter_listings(jobs[0]))
    assert [l.fredy_id for l in listings] == ["x0", "x1", "x2", "x3", "x4"]
    assert calls.count("/api/listings/table") == 3


def test_api_client_login_failure():
    transport = httpx.MockTransport(lambda r: httpx.Response(401))
    with pytest.raises(FredyError, match="Login"):
        FredyApiClient(FredySettings(base_url="http://fredy.test"), "u", "p", transport=transport)


def test_sqlite_client_reads_readonly(tmp_path):
    path = tmp_path / "listings.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE jobs (id TEXT, name TEXT);
        CREATE TABLE listings (id TEXT, hash TEXT, provider TEXT, job_id TEXT, price REAL, size REAL, title TEXT,
                               link TEXT, address TEXT, description TEXT, created_at INTEGER, is_active INTEGER,
                               manually_deleted INTEGER);
        INSERT INTO jobs VALUES ('j1', 'Job 1');
        INSERT INTO listings VALUES ('a', 'h', 'immowelt', 'j1', 300000, 250, 'MFH', 'https://iw.de/a',
                                     '80331 München', 'Text', 1, 1, 0);
        INSERT INTO listings VALUES ('b', 'h2', 'immowelt', 'j1', 1, 1, 'gelöscht', 'https://iw.de/b', '', '', 2, 1, 1);
    """)
    db.commit()
    db.close()

    client = FredySqliteClient(path)
    listings = list(client.iter_listings(client.list_jobs()[0]))
    assert [(l.fredy_id, l.plz, l.preis) for l in listings] == [("a", "80331", 300000)]
    with pytest.raises(sqlite3.OperationalError):
        client._conn.execute("DELETE FROM listings")
    client.close()


def _profile(**fredy) -> Profile:
    return Profile.model_validate({"id": "p", "name": "p", "objektart": "mehrfamilienhaus", "fredy": fredy})


def test_resolve_jobs():
    jobs = [FredyJob("1", "MFH X – IS24"), FredyJob("2", "MFH X – KA"), FredyJob("3", "ETW Y")]
    assert [j.id for j in resolve_jobs(_profile(job_prefix="MFH X"), jobs)] == ["1", "2"]
    assert [j.id for j in resolve_jobs(_profile(jobs=["ETW Y"], job_prefix="MFH X"), jobs)] == ["3", "1", "2"]
    with pytest.raises(ConfigError, match="nicht gefunden"):
        resolve_jobs(_profile(jobs=["Fehlt"]), jobs)
