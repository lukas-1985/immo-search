"""Regelbasierte Extraktion (Quelle `regel`): nur eindeutige Muster, vor allem Attributlisten.

Grundsatz: lieber nichts finden als falsch finden. Regelwerte haben Vorrang vor Claude,
ein Fehler hier würde also eine bessere Claude-Auswertung verdrängen. Deshalb:
- Werte nur aus klaren Bezeichnungen („Mieteinnahmen pro Jahr: 48.000 €“)
- mehrere verschiedene Treffer für dasselbe Feld → kein Wert
- Fließtext („erzielt derzeit monatlich rund …“) bleibt Claude überlassen
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .extraction import ExtractionSchema, load_schema, schema_errors, store_fields
from .models import parse_number

Item = dict[str, Any]

_EURO = r"(?P<num>\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?P<unit>T\s?€|TEUR|Tsd\.?\s?(?:€|EUR|Euro)|€|EUR|Euro)"
_SEP = r"\s*[:=]?\s*(?:ca\.?\s*|rd\.?\s*|rund\s+)?"

_JAHR_LABELS = [
    r"Mieteinnahmen\s+pro\s+Jahr",
    r"Mieteinnahmen\s+p\.?\s?a\.?",
    r"Mieteinnahmen\s+jährlich",
    r"Mieteinnahmen\s*\(Ist\)(?:\s+p\.?\s?a\.?)?",
    r"Jahresnettokaltmiete(?:\s*\(Ist\))?",
    r"Jahresnettomiete(?:\s*\(Ist\))?",
    r"Jahreskaltmiete",
    r"Jahresmiete(?:\s+netto\s+kalt)?",
    r"Ist-?Miete(?:\s+p\.?\s?a\.?|\s+pro\s+Jahr|\s+jährlich)?",
    r"Nettokaltmiete\s+(?:p\.?\s?a\.?|pro\s+Jahr|jährlich)",
]
_MONAT_LABELS = [
    r"Monatliche\s+Mieteinnahmen(?:\s*\(netto\s*kalt\))?",
    r"Monatliche\s+Nettokaltmiete",
    r"Mieteinnahmen\s+(?:monatlich|pro\s+Monat|mtl\.)",
    r"Nettokaltmiete\s+(?:monatlich|pro\s+Monat|mtl\.)",
]
_SOLL_LABELS = [
    r"Jahresnettokaltmiete\s*\(Soll\)",
    r"Mieteinnahmen\s*\(Soll\)(?:\s+p\.?\s?a\.?)?",
    r"Soll-?Miete(?:\s+p\.?\s?a\.?|\s+pro\s+Jahr|\s+jährlich)?",
]
# Nach dem Betrag darf kein Monatsbezug stehen, wenn das Label jährlich ist (und umgekehrt).
_MONATS_SUFFIX = r"(?!\s*(?:/|pro|je|im)\s*(?:Monat|Mon\.|mtl))"


def _line_of(text: str, m: re.Match) -> str:
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    line = text[start : end if end != -1 else len(text)].strip()
    return line if len(line) <= 200 else m.group(0).strip()


def _euro(m: re.Match) -> float | None:
    value = parse_number(m.group("num").replace(" ", "."))
    if value is None:
        return None
    unit = m.group("unit").replace(" ", "").lower()
    return value * 1000 if unit.startswith(("t", "tsd")) else value


def _unique(found: list[tuple[Any, str]], konfidenz: str = "hoch", rechenweg: Callable[[Any], str] | None = None) -> Item | None:
    """Ein Wert nur, wenn alle Treffer übereinstimmen."""
    values = {v for v, _ in found}
    if len(values) != 1:
        return None
    wert, beleg = found[0]
    item: Item = {"wert": wert, "konfidenz": konfidenz, "belegstelle": beleg}
    if rechenweg:
        item["rechenweg"] = rechenweg(wert)
    return item


def _find_euro(text: str, labels: list[str], suffix: str = "") -> list[tuple[float, str, float]]:
    out = []
    for label in labels:
        for m in re.finditer(rf"(?<![\w-])(?:{label}){_SEP}{_EURO}{suffix}", text, re.IGNORECASE):
            v = _euro(m)
            if v:
                out.append((v, _line_of(text, m), parse_number(m.group("num").replace(" ", ".")) or v))
    return out


def _miete_ist(text: str) -> Item | None:
    jahr = _find_euro(text, _JAHR_LABELS, _MONATS_SUFFIX)
    if jahr:
        return _unique([(v, b) for v, b, _ in jahr])
    monat = _find_euro(text, _MONAT_LABELS)
    if monat and len({v for v, _, _ in monat}) == 1:
        v, beleg, _ = monat[0]
        return {"wert": round(v * 12, 2), "konfidenz": "hoch", "belegstelle": beleg,
                "rechenweg": f"{v:,.2f} € × 12 Monate".replace(",", "X").replace(".", ",").replace("X", ".")}
    return None


def _miete_soll(text: str) -> Item | None:
    return _unique([(v, b) for v, b, _ in _find_euro(text, _SOLL_LABELS, _MONATS_SUFFIX)])


def _count(text: str, label_re: str, prose_re: str | None) -> Item | None:
    found = [(int(m.group(1)), _line_of(text, m)) for m in re.finditer(label_re, text, re.IGNORECASE)]
    if found:
        return _unique(found)
    if prose_re:
        found = [(int(m.group(1)), _line_of(text, m)) for m in re.finditer(prose_re, text, re.IGNORECASE)]
        return _unique(found, konfidenz="mittel")
    return None


# Zahl vor „Wohnungen“ usw., aber nicht „davon 2 Wohnungen leer“ / „derzeit 2 Wohnungen frei“,
# nicht „Neubaukonzept für 7 Wohneinheiten“ (Planung) und nicht „5 Wohnungen, 4 Garagen vermietet“ (nur der vermietete Teil)
_NICHT_DAVOR = r"(?<!davon )(?<!derzeit )(?<!noch )(?<!aktuell )(?<!sind )(?<!für )"
_NICHT_DANACH = r"(?!\w*\s+(?:leer|frei|unvermietet|nicht vermietet|stehen leer|sind leer))(?![^.;\n()]{0,25}\bvermietet\b)"


def _wohneinheiten(text: str) -> Item | None:
    return _count(
        text,
        r"(?:Anzahl\s+(?:der\s+)?Wohneinheiten|Wohneinheiten(?:\s+gesamt)?)\s*:\s*(\d{1,3})\b",
        rf"{_NICHT_DAVOR}\b(\d{{1,3}})\s*-?\s*(?:Wohneinheiten|Wohnungen|WE\b|Whg\b\.?|Parteien){_NICHT_DANACH}",
    )


def _gewerbeeinheiten(text: str) -> Item | None:
    return _count(
        text,
        r"Anzahl\s+(?:der\s+)?Gewerbeeinheiten\s*:\s*(\d{1,3})\b",
        rf"{_NICHT_DAVOR}\b(\d{{1,3}})\s*-?\s*Gewerbeeinheit(?:en)?\b{_NICHT_DANACH}",
    )


def _provision(text: str) -> Item | None:
    found: list[tuple[float, str]] = []
    for m in re.finditer(r"(?<!nicht )\bprovisionsfrei\b|\bkeine\s+(?:Käufer|Makler)?provision\b", text, re.IGNORECASE):
        found.append((0.0, _line_of(text, m)))
    pattern = r"(?:Käuferprovision|Käufercourtage|Maklerprovision|Provision|Courtage)[^\d\n%]{0,40}?(\d{1,2}(?:[.,]\d{1,2})?)\s*%"
    for m in re.finditer(pattern, text, re.IGNORECASE):
        found.append((round(float(m.group(1).replace(",", ".")) / 100, 4), _line_of(text, m)))
    return _unique(found)


def _grundstueck(text: str) -> Item | None:
    found = []
    for m in re.finditer(r"Grundstück(?:sfläche|sgröße|s?größe)?\s*:?\s*(?:ca\.?\s*|von\s+)?(\d{1,3}(?:\.\d{3})*|\d+)\s*(?:m²|m2|qm)\b", text, re.IGNORECASE):
        found.append((parse_number(m.group(1)), _line_of(text, m)))
    return _unique(found)


def _janein(text: str, ja: str, nein: str, ja_konfidenz: str = "hoch") -> Item | None:
    """Ja/Nein aus festen Formulierungen; widersprüchliche Treffer → kein Wert."""
    neg = [(False, _line_of(text, m)) for m in re.finditer(nein, text, re.IGNORECASE)]
    # Positive Treffer, die in einer Verneinung liegen, nicht doppelt zählen
    neg_spans = [m.span() for m in re.finditer(nein, text, re.IGNORECASE)]
    pos = [
        (True, _line_of(text, m))
        for m in re.finditer(ja, text, re.IGNORECASE)
        if not any(s <= m.start() < e for s, e in neg_spans)
    ]
    item = _unique(neg + pos, konfidenz=ja_konfidenz if pos and not neg else "hoch")
    return item


def _erbpacht(text: str) -> Item | None:
    return _janein(
        text,
        r"\b(?:Erbpacht|Erbbaurecht|Erbbaurechts|Erbbauzins)\w*",
        r"\b(?:kein(?:e|en)?|ohne|nicht\s+im)\s+(?:Erbpacht|Erbbaurecht)\w*|\b(?:Erbpacht|Erbbaurecht)\s*:\s*nein\b",
        ja_konfidenz="mittel",
    )


def _denkmalschutz(text: str) -> Item | None:
    return _janein(
        text,
        r"\bdenkmalgeschützt\w*|\bDenkmalschutz\b|\b(?:Bau|Einzel)denkmal\b",
        r"\b(?:kein(?:en)?\s+Denkmalschutz|nicht\s+denkmalgeschützt\w*)|\bDenkmalschutz\s*:\s*nein\b",
        ja_konfidenz="mittel",
    )


def _aufgeteilt(text: str) -> Item | None:
    return _janein(
        text,
        r"\bnach\s+(?:WEG|WEG-Recht)\s+aufgeteilt\b|\bTeilungserklärung\s+(?:liegt\s+vor|ist\s+vorhanden|vorhanden)\b|\bbereits\s+aufgeteilt\b",
        r"\bnicht\s+(?:nach\s+WEG\s+)?aufgeteilt\b|\bkeine\s+Teilungserklärung\b",
    )


def _verhandlungsbasis(text: str) -> Item | None:
    return _janein(text, r"\bVB\b|\bVerhandlungsbasis\b|\bverhandelbar\b", r"\bFestpreis\b|\bnicht\s+verhandelbar\b")


def _heizungsart(text: str) -> Item | None:
    for label in (r"Heizungsart", r"Heizung", r"Befeuerungsart", r"Befeuerung", r"Wesentliche\s+Energieträger", r"Energieträger"):
        found = [
            (m.group(1).strip(" .,;"), _line_of(text, m))
            for m in re.finditer(rf"(?<![\w-]){label}\s*:\s*([^\W\d_][^\n;:]{{1,59}}?)\s*(?:$|\n|;|\.\s)", text, re.IGNORECASE | re.MULTILINE)
        ]
        if found:
            return _unique(found)
    return None


def _heizung_baujahr(text: str) -> Item | None:
    found = [
        (int(m.group(1)), _line_of(text, m))
        for m in re.finditer(r"(?:Baujahr\s+(?:der\s+)?Heizung|Heizung\s*(?:\(|,)?\s*Baujahr|Heizungsbaujahr)\s*:?\s*\)?\s*((?:19|20)\d\d)\b", text, re.IGNORECASE)
    ]
    return _unique(found)


_ZUSTAND = {
    "neuwertig": "neuwertig", "erstbezug": "neuwertig", "neubau": "neuwertig", "erstbezug nach sanierung": "neuwertig",
    "vollständig renoviert": "neuwertig", "vollständig saniert": "neuwertig",
    "gepflegt": "gepflegt", "modernisiert": "gepflegt", "saniert": "gepflegt", "renoviert": "gepflegt",
    "renovierungsbedürftig": "renovierungsbeduerftig", "sanierungsbedürftig": "renovierungsbeduerftig",
    "baufällig": "sanierungsstau", "abrissobjekt": "sanierungsstau",
}


def _zustand(text: str) -> Item | None:
    found = []
    for m in re.finditer(r"(?:Objektzustand|Zustand)\s*:\s*([^\n,;]{3,40})", text, re.IGNORECASE):
        key = m.group(1).strip(" .").casefold()
        if key in _ZUSTAND:
            found.append((_ZUSTAND[key], _line_of(text, m)))
    return _unique(found)


RULES: dict[str, Callable[[str], Item | None]] = {
    "jahresnettokaltmiete_ist": _miete_ist,
    "jahresnettokaltmiete_soll": _miete_soll,
    "wohneinheiten": _wohneinheiten,
    "gewerbeeinheiten": _gewerbeeinheiten,
    "provision": _provision,
    "grundstueck_m2": _grundstueck,
    "erbpacht": _erbpacht,
    "denkmalschutz": _denkmalschutz,
    "aufgeteilt_weg": _aufgeteilt,
    "verhandlungsbasis": _verhandlungsbasis,
    "heizungsart": _heizungsart,
    "heizung_baujahr": _heizung_baujahr,
    "zustand": _zustand,
}


def extract_rules(titel: str | None, beschreibung: str | None, schema: ExtractionSchema) -> dict[str, Item]:
    text = "\n".join(t for t in (titel, beschreibung) if t)
    out: dict[str, Item] = {}
    for feld, rule in RULES.items():
        if feld not in schema.fields:
            continue
        if (item := rule(text)) is not None:
            out[feld] = item
    # Gegenprobe gegen das Schema: ein Regelwert, der nicht passt, wird verworfen
    for feld in list(out):
        if schema_errors(schema, {"listing_id": 0, "beschreibung_hash": "", "felder": {feld: out[feld]}}):
            del out[feld]
    return out


@dataclass
class ParseStats:
    angebote: int = 0
    felder: int = 0
    abgelehnt: dict[str, int] = field(default_factory=dict)


def run_parse_attrs(conn: sqlite3.Connection, objektart_by_listing: dict[int, str]) -> ParseStats:
    """Regeln auf alle übergebenen Angebote anwenden; Regelwerte werden jeweils komplett ersetzt."""
    stats = ParseStats()
    for listing_id, objektart in objektart_by_listing.items():
        schema = load_schema(objektart)
        row = conn.execute("SELECT * FROM listing WHERE id = ?", (listing_id,)).fetchone()
        felder = extract_rules(row["titel"], row["beschreibung"], schema)
        report = store_fields(conn, row, felder, "regel", schema.version)
        stats.angebote += 1
        stats.felder += len(report.gespeichert)
        for feld in report.abgelehnt:
            stats.abgelehnt[feld] = stats.abgelehnt.get(feld, 0) + 1
    conn.commit()
    return stats
