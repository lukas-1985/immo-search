"""Filterstufe 2 (`fetch_filter`): wirkt in `sync` vor dem Speichern, nur auf Fredy-Felder."""

from __future__ import annotations

import math

from .config import FetchFilter, LocationFilter, Range
from .models import FredyListing


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _ort_matches(ort: str, orte: list[str]) -> bool:
    o = ort.casefold()
    for wanted in orte:
        w = wanted.casefold()
        if o == w or o.startswith(w + " ") or o.startswith(w + "-") or o.startswith(w + " ("):
            return True
    return False


def _location_reason(listing: FredyListing, loc: LocationFilter) -> str | None:
    if not loc.is_set:
        return None
    has_coords = listing.lat is not None and listing.lon is not None
    if not (listing.plz or listing.ort or has_coords):
        return "ort_fehlt" if loc.on_missing == "drop" else None
    # Ein Ortskriterium reicht (ODER-Verknüpfung): PLZ-Präfix, Ortsname oder Umkreis.
    if loc.plz_prefix and listing.plz and any(listing.plz.startswith(p) for p in loc.plz_prefix):
        return None
    if loc.orte and listing.ort and _ort_matches(listing.ort, loc.orte):
        return None
    if loc.umkreis and has_coords:
        if haversine_km(listing.lat, listing.lon, loc.umkreis.lat, loc.umkreis.lon) <= loc.umkreis.km:  # type: ignore[arg-type]
            return None
    return "ort"


def _range_reason(name: str, value: float | None, rng: Range) -> str | None:
    # Fehlender Wert: behalten – Stufe 3 (hard_filter) kann später genauer entscheiden.
    if value is None or not rng.is_set:
        return None
    return None if rng.contains(value) else name


def fetch_filter_reason(listing: FredyListing, ff: FetchFilter) -> str | None:
    """Grund, warum das Angebot nicht gespeichert wird – oder None, wenn es passt."""
    if ff.providers and listing.provider not in ff.providers:
        return "portal"
    titel = (listing.titel or "").casefold()
    if any(k.casefold() in titel for k in ff.exclude_keywords):
        return "stichwort"
    for reason in (
        _range_reason("preis", listing.preis, ff.preis),
        _range_reason("wohnflaeche", listing.flaeche, ff.wohnflaeche),
        _range_reason("zimmer", listing.zimmer, ff.zimmer),
        _range_reason("baujahr", listing.baujahr, ff.baujahr),
        _location_reason(listing, ff.location),
    ):
        if reason:
            return reason
    return None
