"""Nur Entwicklung: Testanzeigen aus einer JSON-Datei über den normalen Sync in eine DB laden.

    python scripts/dev_seed.py --db data/dev.db [--profile mfh-beispiel] [tests/fixtures/mfh_anzeigen.json]

Nutzt statt Fredy einen Fake-Client, der alle Anzeigen im ersten Job des Profils liefert.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from immo.cli import open_context, parser, print_json, run
from immo.config import PROJECT_ROOT
from immo.models import FredyJob, FredyListing
from immo.sync import run_sync


class FixtureClient:
    def __init__(self, job_names: list[str], listings: list[FredyListing]):
        self._jobs = [FredyJob(id=f"dev-{i}", name=n) for i, n in enumerate(job_names)]
        self._listings = listings

    def list_jobs(self) -> list[FredyJob]:
        return self._jobs

    def iter_listings(self, job: FredyJob) -> Iterator[FredyListing]:
        if job == self._jobs[0]:
            yield from self._listings

    def close(self) -> None:
        pass


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--profile", default="mfh-beispiel")
    ap.add_argument("datei", nargs="?", type=Path, default=PROJECT_ROOT / "tests" / "fixtures" / "mfh_anzeigen.json")
    args = ap.parse_args()
    if not args.db:
        ap.error("--db angeben (nie in die echte DB laden)")

    config, conn = open_context(args)
    profile = config.profiles[args.profile]
    fixtures = json.loads(args.datei.read_text(encoding="utf-8"))
    listings = [
        FredyListing(fredy_id=f"dev{fx['nr']}", provider=fx["provider"], url=f"https://example.test/{fx['nr']}",
                     titel=fx["titel"], adresse=fx["adresse"], preis=fx["preis"], flaeche=fx["flaeche"],
                     baujahr=fx["baujahr"], beschreibung=fx["beschreibung"])
        for fx in fixtures
    ]
    names = profile.fredy.jobs or [f"{profile.fredy.job_prefix} dev"]
    stats = run_sync(conn, FixtureClient(names, listings), config, profile.id)
    conn.close()
    print_json({s.profile_id: s.as_dict() for s in stats})
    return 0


if __name__ == "__main__":
    run(main)
