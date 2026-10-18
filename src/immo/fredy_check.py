"""Diagnose gegen ein laufendes Fredy (Phase 1): beantwortet die offenen Punkte aus PLAN.md 14.

Liest nur – schreibt weder in Fredy noch in die eigene DB.
"""

from __future__ import annotations

import difflib
import statistics
from collections import Counter
from typing import Any

from .config import Config, ConfigError
from .extraction import load_schema
from .filters import fetch_filter_reason
from .fredy_client import FredyError, RawFredyClient, listing_from_row, resolve_jobs
from .models import FredyJob, FredyListing
from .parse_attrs import extract_rules

# Rohfelder, die listing_from_row liest (snake_case und camelCase)
GELESEN = {
    "id", "hash", "provider", "link", "url", "job_id", "jobId", "title", "address", "latitude", "lat", "longitude", "lon", "lng",
    "price", "size", "rooms", "build_year", "buildYear", "energy_class", "energyClass", "description", "images", "image_url",
    "imageUrl", "created_at", "createdAt", "is_active", "isActive",
}
# Hinweise auf eine Duplikat-Kennung in Fredys Daten (offener Punkt 5)
DUPLIKAT_HINWEISE = ("dup", "similar", "group", "same", "twin")


def _anteil(n: int, gesamt: int) -> float | None:
    return round(n / gesamt, 3) if gesamt else None


def _abdeckung(listings: list[FredyListing]) -> dict[str, float | None]:
    n = len(listings)
    return {
        "preis": _anteil(sum(l.preis is not None for l in listings), n),
        "flaeche": _anteil(sum(l.flaeche is not None for l in listings), n),
        "zimmer": _anteil(sum(l.zimmer is not None for l in listings), n),
        "baujahr": _anteil(sum(l.baujahr is not None for l in listings), n),
        "adresse": _anteil(sum(bool(l.adresse) for l in listings), n),
        "plz": _anteil(sum(l.plz is not None for l in listings), n),
        "ort": _anteil(sum(l.ort is not None for l in listings), n),
        "koordinaten": _anteil(sum(l.lat is not None and l.lon is not None for l in listings), n),
        "beschreibung": _anteil(sum(bool(l.beschreibung) for l in listings), n),
        "bilder": _anteil(sum(bool(l.bilder) for l in listings), n),
    }


def _textlaengen(listings: list[FredyListing]) -> dict[str, Any] | None:
    laengen = [len(l.beschreibung) for l in listings if l.beschreibung]
    if not laengen:
        return None
    return {
        "min": min(laengen), "median": int(statistics.median(laengen)), "max": max(laengen),
        "anteil_unter_300_zeichen": _anteil(sum(x < 300 for x in laengen), len(laengen)),
        # Fredy oder das Portal kürzt? Viele Texte mit identischer Maximallänge oder „…“ am Ende sind ein Hinweis
        "enden_mit_auslassung": sum(l.beschreibung.rstrip().endswith(("…", "...")) for l in listings if l.beschreibung),
        "haeufigste_laenge": Counter(laengen).most_common(1)[0],
    }


def _duplikat_kandidaten(alle: list[FredyListing]) -> list[dict[str, Any]]:
    """Gleiche PLZ + ähnliche Fläche (±2 %) + ähnlicher Preis (±5 %) auf verschiedenen Portalen."""
    kandidaten = []
    nach_plz: dict[str, list[FredyListing]] = {}
    for l in alle:
        if l.plz and l.flaeche and l.preis:
            nach_plz.setdefault(l.plz, []).append(l)
    for plz, gruppe in nach_plz.items():
        for i, a in enumerate(gruppe):
            for b in gruppe[i + 1 :]:
                if a.provider != b.provider and abs(a.flaeche - b.flaeche) <= 0.02 * a.flaeche \
                        and abs(a.preis - b.preis) <= 0.05 * a.preis:  # type: ignore[operator]
                    kandidaten.append({"plz": plz, "a": [a.provider, a.titel, a.url], "b": [b.provider, b.titel, b.url]})
    return kandidaten[:20]


def check(client: RawFredyClient, config: Config, stichprobe: int = 3) -> tuple[dict[str, Any], dict[str, Any]]:
    """Liefert (Bericht, Rohdaten-Stichprobe)."""
    bericht: dict[str, Any] = {"verbindung": "ok"}
    roh: dict[str, Any] = {}

    raw_jobs = client.raw_jobs()
    jobs = [FredyJob(id=str(j["id"]), name=str(j["name"])) for j in raw_jobs]
    bericht["jobs"] = [
        {"id": j.get("id"), "name": j.get("name"), "aktiv": j.get("enabled"), "felder": sorted(j)} for j in raw_jobs
    ]
    roh["jobs"] = raw_jobs

    # Profile ↔ Jobs (offener Punkt 6)
    namen = [j.name for j in jobs]
    profile: dict[str, Any] = {}
    for p in config.active_profiles():
        try:
            gefunden = [j.name for j in resolve_jobs(p, jobs)]
            profile[p.id] = {"jobs": gefunden, "fehlend": []}
        except ConfigError:
            fehlend = [n for n in p.fredy.jobs if n not in namen]
            profile[p.id] = {
                "jobs": [n for n in p.fredy.jobs if n in namen],
                "fehlend": [{"name": n, "aehnlich": difflib.get_close_matches(n, namen, n=2, cutoff=0.6)} for n in fehlend],
            }
    bericht["profile"] = profile

    alle: list[FredyListing] = []
    bericht["je_job"] = {}
    roh["listings"] = {}
    schema = load_schema("mehrfamilienhaus")
    for job in jobs:
        try:
            rows = list(client.iter_raw(job))
        except FredyError as exc:
            bericht["je_job"][job.name] = {"fehler": str(exc)}
            continue
        listings, abbildfehler = [], 0
        for r in rows:
            try:
                listings.append(listing_from_row(r, job))
            except FredyError:
                abbildfehler += 1
        alle += listings

        rohfelder = sorted({k for r in rows for k in r})
        erstellt = sorted(str(r.get("created_at") or r.get("createdAt") or "") for r in rows)
        regel_miete = sum("jahresnettokaltmiete_ist" in extract_rules(l.titel, l.beschreibung, schema) for l in listings)
        bericht["je_job"][job.name] = {
            "anzahl": len(rows),
            "aktiv": sum(l.is_active for l in listings),
            "portale": dict(Counter(l.provider for l in listings)),
            "abbildungsfehler": abbildfehler,
            "abdeckung": _abdeckung(listings),
            "beschreibung": _textlaengen(listings),
            "rohfelder": rohfelder,
            "nicht_gelesen": [k for k in rohfelder if k not in GELESEN],
            "duplikat_felder": [k for k in rohfelder if any(h in k.lower() for h in DUPLIKAT_HINWEISE)],
            "erstellt_von_bis": [erstellt[0], erstellt[-1]] if erstellt else None,
            "regel_findet_ist_miete": _anteil(regel_miete, len(listings)),
        }
        roh["listings"][job.name] = rows[:stichprobe]

    # fetch_filter-Vorschau je Profil
    jobs_by_name = {j.name: j for j in jobs}
    for pid, info in profile.items():
        p = config.profiles[pid]
        job_ids = {jobs_by_name[n].id for n in info["jobs"]}
        betroffen = [l for l in alle if l.job_id in job_ids]
        gruende = Counter(fetch_filter_reason(l, p.fetch_filter) or "passt" for l in betroffen)
        info["fetch_filter"] = dict(gruende)

    bericht["duplikat_kandidaten"] = _duplikat_kandidaten(alle)
    bericht["gesamt"] = {"angebote": len(alle), "portale": dict(Counter(l.provider for l in alle))}
    return bericht, roh
