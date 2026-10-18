from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from immo.config import load_config
from immo.db import connect
from immo.fredy_client import FredyError
from immo.models import FredyJob, FredyListing

SETTINGS = """
fredy: { base_url: "http://fredy.test", access: api }
database: { path: "data/immo.db" }
grunderwerbsteuer: { BY: 0.035 }
"""

PROFILE_A = """
id: mfh-a
name: "MFH A"
objektart: mehrfamilienhaus
fredy: { jobs: ["Job IS24", "Job KA"] }
fetch_filter:
  location: { plz_prefix: ["80"], orte: ["Freising"] }
  preis: { max: 1000000 }
  exclude_keywords: ["Zwangsversteigerung"]
"""

PROFILE_B = """
id: mfh-b
name: "MFH B"
objektart: mehrfamilienhaus
fredy: { job_prefix: "Job" }
fetch_filter:
  preis: { max: 500000 }
"""


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "config"
    (d / "profiles").mkdir(parents=True)
    (d / "settings.yaml").write_text(SETTINGS, encoding="utf-8")
    (d / "profiles" / "mfh-a.yaml").write_text(PROFILE_A, encoding="utf-8")
    return d


@pytest.fixture
def config(config_dir: Path):
    return load_config(config_dir)


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def make_listing(n: int, **kw) -> FredyListing:
    defaults = dict(
        fredy_id=f"f{n}",
        provider="immoscout",
        url=f"https://www.immobilienscout24.de/expose/{n}",
        titel=f"MFH {n}",
        adresse="Hauptstr. 1, 80331 München",
        preis=800_000,
        flaeche=400,
        beschreibung=f"Schönes Haus {n}",
    )
    defaults.update(kw)
    return FredyListing(**defaults)


class FakeClient:
    def __init__(self, jobs: dict[str, list[FredyListing]]):
        self.jobs = jobs
        self.failing: set[str] = set()

    def list_jobs(self) -> list[FredyJob]:
        return [FredyJob(id=name.lower().replace(" ", "-"), name=name) for name in self.jobs]

    def iter_listings(self, job: FredyJob) -> Iterator[FredyListing]:
        if job.name in self.failing:
            raise FredyError("kaputt")
        yield from self.jobs[job.name]

    def close(self) -> None:
        pass
