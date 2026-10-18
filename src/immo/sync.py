"""Schritt 1 eines Laufs: Angebote der Profil-Jobs von Fredy holen und in der eigenen DB führen.

- Neue Angebote durchlaufen den `fetch_filter`; abgelehnte werden nur gezählt.
- Bekannte Angebote werden immer aktualisiert (Preis → price_history, Beschreibung → Hash).
- Bekannte Angebote, die Fredy nicht mehr liefert oder als inaktiv meldet, gelten als „entfernt“.
- Beliebig oft ausführbar: Schlüssel ist (provider, url), es entstehen keine Duplikate.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from .config import Config, Profile
from .db import now_iso
from .filters import fetch_filter_reason
from .fredy_client import FredyClient, FredyError, resolve_jobs
from .models import FredyListing

# Felder, die bei bekannten Angeboten aus Fredy übernommen werden (nur wenn Fredy einen Wert liefert)
_UPDATABLE = ("titel", "adresse", "plz", "ort", "lat", "lon", "flaeche", "zimmer", "baujahr", "energieklasse")


@dataclass
class SyncStats:
    profile_id: str
    geholt: int = 0
    neu: int = 0
    aktualisiert: int = 0
    preisaenderungen: int = 0
    beschreibung_geaendert: int = 0
    entfernt: int = 0
    reaktiviert: int = 0
    inaktiv_ignoriert: int = 0
    gefiltert: Counter[str] = field(default_factory=Counter)
    fehler: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("profile_id", "gefiltert")}
        d["gefiltert"] = dict(self.gefiltert)
        return d


def text_hash(text: str | None) -> str | None:
    if not text:
        return None
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def _insert(conn: sqlite3.Connection, l: FredyListing, ts: str) -> int:
    cur = conn.execute(
        """INSERT INTO listing (fredy_id, fredy_hash, provider, url, titel, adresse, plz, ort, lat, lon, preis,
               flaeche, zimmer, baujahr, energieklasse, beschreibung, beschreibung_hash, bilder,
               first_seen, last_seen, status_portal)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aktiv')""",
        (l.fredy_id, l.fredy_hash, l.provider, l.url, l.titel, l.adresse, l.plz, l.ort, l.lat, l.lon, l.preis,
         l.flaeche, l.zimmer, l.baujahr, l.energieklasse, l.beschreibung, text_hash(l.beschreibung),
         json.dumps(l.bilder, ensure_ascii=False), ts, ts),
    )
    listing_id = cur.lastrowid
    # Duplikaterkennung über Portale folgt später; bis dahin bildet jedes Angebot eine eigene Gruppe.
    conn.execute("UPDATE listing SET duplicate_group = ? WHERE id = ?", (listing_id, listing_id))
    if l.preis is not None:
        conn.execute("INSERT INTO price_history (listing_id, datum, preis) VALUES (?, ?, ?)", (listing_id, ts, l.preis))
    return listing_id  # type: ignore[return-value]


def _update(conn: sqlite3.Connection, row: sqlite3.Row, l: FredyListing, ts: str, stats: SyncStats) -> None:
    sets: dict[str, object] = {"last_seen": ts}
    for name in _UPDATABLE:
        value = getattr(l, name)
        if value is not None and value != row[name]:
            sets[name] = value
    if l.bilder:
        bilder = json.dumps(l.bilder, ensure_ascii=False)
        if bilder != row["bilder"]:
            sets["bilder"] = bilder
    if l.beschreibung:
        h = text_hash(l.beschreibung)
        if h != row["beschreibung_hash"]:
            sets.update(beschreibung=l.beschreibung, beschreibung_hash=h)
            stats.beschreibung_geaendert += 1
    if l.preis is not None and l.preis != row["preis"]:
        sets["preis"] = l.preis
        conn.execute("INSERT INTO price_history (listing_id, datum, preis) VALUES (?, ?, ?)", (row["id"], ts, l.preis))
        stats.preisaenderungen += 1

    status = "aktiv" if l.is_active else "entfernt"
    if status != row["status_portal"]:
        sets["status_portal"] = status
        if status == "aktiv":
            stats.reaktiviert += 1
        else:
            stats.entfernt += 1

    if len(sets) > 1:
        stats.aktualisiert += 1
    cols = ", ".join(f"{k} = ?" for k in sets)
    conn.execute(f"UPDATE listing SET {cols} WHERE id = ?", (*sets.values(), row["id"]))


def _link(conn: sqlite3.Connection, listing_id: int, profile_id: str, job_id: str | None, ts: str) -> None:
    conn.execute(
        """INSERT INTO listing_profile (listing_id, profile_id, fredy_job_id, first_seen) VALUES (?, ?, ?, ?)
           ON CONFLICT (listing_id, profile_id) DO UPDATE SET fredy_job_id = excluded.fredy_job_id""",
        (listing_id, profile_id, job_id, ts),
    )


def sync_profile(
    conn: sqlite3.Connection, client: FredyClient, profile: Profile, jobs_all, ts: str, seen: set[int], ok_jobs: set[str]
) -> SyncStats:
    """Holt die Jobs eines Profils. `seen`/`ok_jobs` sammeln profilübergreifend, was Fredy geliefert hat."""
    stats = SyncStats(profile.id)
    for job in resolve_jobs(profile, jobs_all):
        try:
            listings = list(client.iter_listings(job))
        except FredyError as exc:
            # Job nicht abrufbar: nichts als „entfernt“ markieren, Rest des Profils weiter abarbeiten.
            stats.fehler.append(f"{job.name}: {exc}")
            continue
        ok_jobs.add(job.id)

        for l in listings:
            stats.geholt += 1
            row = conn.execute("SELECT * FROM listing WHERE provider = ? AND url = ?", (l.provider, l.url)).fetchone()
            if row is not None:
                _update(conn, row, l, ts, stats)
                seen.add(row["id"])
            linked = row is not None and conn.execute(
                "SELECT 1 FROM listing_profile WHERE listing_id = ? AND profile_id = ?", (row["id"], profile.id)
            ).fetchone()
            if not linked:
                # Neu für dieses Profil: erst durch dessen fetch_filter
                reason = fetch_filter_reason(l, profile.fetch_filter)
                if reason:
                    stats.gefiltert[reason] += 1
                    continue
                if row is None:
                    if not l.is_active:
                        stats.inaktiv_ignoriert += 1
                        continue
                    listing_id = _insert(conn, l, ts)
                    seen.add(listing_id)
                    stats.neu += 1
                else:
                    listing_id = row["id"]
            else:
                listing_id = row["id"]
            _link(conn, listing_id, profile.id, job.id, ts)
        conn.commit()  # kurze Transaktion je Job
    return stats


def _mark_removed(conn: sqlite3.Connection, seen: set[int], ok_jobs: set[str], stats_by_profile: dict[str, SyncStats]) -> None:
    """Aktive Angebote erfolgreich abgerufener Jobs, die kein Job mehr geliefert hat → entfernt."""
    if not ok_jobs:
        return
    marks = ",".join("?" * len(ok_jobs))
    rows = conn.execute(
        f"""SELECT DISTINCT l.id, lp.profile_id FROM listing l JOIN listing_profile lp ON lp.listing_id = l.id
            WHERE l.status_portal = 'aktiv' AND lp.fredy_job_id IN ({marks})""",
        tuple(ok_jobs),
    ).fetchall()
    gone = {r["id"] for r in rows if r["id"] not in seen}
    for r in rows:
        if r["id"] in gone and r["profile_id"] in stats_by_profile:
            stats_by_profile[r["profile_id"]].entfernt += 1
    conn.executemany("UPDATE listing SET status_portal = 'entfernt' WHERE id = ?", [(i,) for i in gone])
    conn.commit()


def run_sync(conn: sqlite3.Connection, client: FredyClient, config: Config, only_profile: str | None = None) -> list[SyncStats]:
    profiles = config.active_profiles(only_profile)
    jobs_all = client.list_jobs()
    seen: set[int] = set()
    ok_jobs: set[str] = set()
    results: dict[str, tuple[str, SyncStats]] = {}
    for profile in profiles:
        start = now_iso()
        results[profile.id] = (start, sync_profile(conn, client, profile, jobs_all, start, seen, ok_jobs))
    _mark_removed(conn, seen, ok_jobs, {pid: s for pid, (_, s) in results.items()})

    for profile_id, (start, stats) in results.items():
        conn.execute(
            "INSERT INTO run_log (schritt, profile_id, start, ende, zahlen_json, fehler) VALUES ('sync', ?, ?, ?, ?, ?)",
            (profile_id, start, now_iso(), json.dumps(stats.as_dict(), ensure_ascii=False), "\n".join(stats.fehler) or None),
        )
    conn.commit()
    return [s for _, s in results.values()]
