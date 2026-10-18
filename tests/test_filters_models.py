import pytest

from immo.config import FetchFilter
from immo.filters import fetch_filter_reason, haversine_km
from immo.fredy_client import listing_from_row
from immo.models import normalize_url, parse_number, parse_plz_ort

from .conftest import make_listing


@pytest.mark.parametrize(
    "raw, expected",
    [(450000, 450000.0), ("450.000 €", 450000.0), ("1.234,5 m²", 1234.5), ("3,5", 3.5), ("12.5", 12.5),
     ("1.250.000", 1250000.0), ("k. A.", None), (None, None)],
)
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected


def test_parse_plz_ort():
    assert parse_plz_ort("Hauptstr. 1, 80331 München") == ("80331", "München")
    assert parse_plz_ort("85354 Freising (Lerchenfeld)") == ("85354", "Freising (Lerchenfeld)")
    assert parse_plz_ort("München") == (None, None)


def test_normalize_url():
    assert normalize_url("https://WWW.Example.de/expose/1/?ref=x#top") == "https://www.example.de/expose/1"


def test_listing_from_row_snake_and_camel():
    snake = listing_from_row({"id": 1, "provider": "Immowelt", "link": "https://iw.de/1", "price": "500.000 €",
                              "size": 300, "build_year": "1965", "is_active": 0, "address": "80331 München"})
    camel = listing_from_row({"id": "2", "provider": "kleinanzeigen", "url": "https://ka.de/2", "buildYear": 1970,
                              "isActive": True, "imageUrl": "https://img/1.jpg"})
    assert (snake.provider, snake.preis, snake.baujahr, snake.is_active, snake.plz) == ("immowelt", 500000, 1965, False, "80331")
    assert (camel.baujahr, camel.is_active, camel.bilder) == (1970, True, ["https://img/1.jpg"])


def ff(**kw) -> FetchFilter:
    return FetchFilter.model_validate(kw)


def test_no_filter_keeps_everything():
    assert fetch_filter_reason(make_listing(1), ff()) is None


@pytest.mark.parametrize(
    "listing_kw, filter_kw, reason",
    [
        ({"preis": 2_000_000}, {"preis": {"max": 1_000_000}}, "preis"),
        ({"preis": None}, {"preis": {"max": 1_000_000}}, None),  # fehlender Wert → behalten
        ({"flaeche": 100}, {"wohnflaeche": {"min": 200}}, "wohnflaeche"),
        ({"provider": "immonet"}, {"providers": ["immoscout"]}, "portal"),
        ({"titel": "ZWANGSVERSTEIGERUNG MFH"}, {"exclude_keywords": ["Zwangsversteigerung"]}, "stichwort"),
        ({}, {"location": {"plz_prefix": ["80"]}}, None),
        ({}, {"location": {"plz_prefix": ["85"]}}, "ort"),
        ({"adresse": "85354 Freising-Lerchenfeld"}, {"location": {"orte": ["freising"]}}, None),
        ({"adresse": None}, {"location": {"orte": ["Freising"]}}, None),
        ({"adresse": None}, {"location": {"orte": ["Freising"], "on_missing": "drop"}}, "ort_fehlt"),
        ({"adresse": None, "lat": 48.14, "lon": 11.58}, {"location": {"umkreis": {"lat": 48.40, "lon": 11.75, "km": 40}}}, None),
        ({"adresse": None, "lat": 48.14, "lon": 11.58}, {"location": {"umkreis": {"lat": 48.40, "lon": 11.75, "km": 20}}}, "ort"),
    ],
)
def test_fetch_filter(listing_kw, filter_kw, reason):
    assert fetch_filter_reason(make_listing(1, **listing_kw), ff(**filter_kw)) == reason


def test_haversine_munich_freising():
    assert 30 < haversine_km(48.14, 11.58, 48.40, 11.75) < 33
