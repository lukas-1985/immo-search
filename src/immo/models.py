"""Datenmodelle, die zwischen Fredy-Client, Filtern und Sync ausgetauscht werden."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

_PLZ_ORT = re.compile(r"\b(\d{5})\s+([^,\d][^,]*)")
_NUMBER = re.compile(r"-?\d[\d.,]*")


@dataclass(frozen=True)
class FredyJob:
    id: str
    name: str


@dataclass
class FredyListing:
    """Ein Angebot, wie Fredy es liefert, auf unsere Feldnamen abgebildet."""

    fredy_id: str
    provider: str
    url: str
    job_id: str | None = None
    fredy_hash: str | None = None
    titel: str | None = None
    adresse: str | None = None
    plz: str | None = None
    ort: str | None = None
    lat: float | None = None
    lon: float | None = None
    preis: float | None = None
    flaeche: float | None = None
    zimmer: float | None = None
    baujahr: int | None = None
    energieklasse: str | None = None
    beschreibung: str | None = None
    bilder: list[str] = field(default_factory=list)
    created_at: str | None = None
    is_active: bool = True

    def __post_init__(self) -> None:
        self.url = normalize_url(self.url)
        if self.adresse and (self.plz is None or self.ort is None):
            plz, ort = parse_plz_ort(self.adresse)
            self.plz = self.plz or plz
            self.ort = self.ort or ort


def normalize_url(url: str) -> str:
    """Query und Fragment entfernen, damit dasselbe Angebot immer denselben Schlüssel hat."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def parse_plz_ort(adresse: str) -> tuple[str | None, str | None]:
    m = _PLZ_ORT.search(adresse)
    if not m:
        return None, None
    return m.group(1), m.group(2).strip() or None


def parse_number(value: object) -> float | None:
    """Zahlen aus Fredy tolerant lesen: 450000, "450.000 €", "1.234,5 m²", "3,5"."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    m = _NUMBER.search(str(value))
    if not m:
        return None
    s = m.group(0)
    if "," in s:  # deutsches Format: Punkt = Tausender, Komma = Dezimal
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None
