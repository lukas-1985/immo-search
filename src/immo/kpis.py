"""KPI-Register: jede Kennzahl ist eine benannte Funktion → (wert, qualität) oder None.

Neue KPIs hier eintragen; danach sind sie per Konfiguration in Score, Ausschlusskriterien
und (später) Oberfläche und Simulation nutzbar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .config import Normalize
from .finance import Ergebnis, Qualitaet

KpiWert = tuple[float, Qualitaet] | None


@dataclass(frozen=True)
class Kontext:
    ergebnis: Ergebnis
    flaeche: float | None
    marktmiete_eur_m2: float | None


@dataclass(frozen=True)
class Kpi:
    name: str
    beschreibung: str
    einheit: str
    fn: Callable[[Kontext], KpiWert]


def _miete(ctx: Kontext, wert: float | None) -> KpiWert:
    q = ctx.ergebnis.annahmen.miete_qualitaet
    return None if wert is None or q is None else (wert, q)


def _bruttorendite(ctx: Kontext) -> KpiWert:
    return _miete(ctx, ctx.ergebnis.bruttorendite)


def _faktor(ctx: Kontext) -> KpiWert:
    return _miete(ctx, ctx.ergebnis.faktor)


def _nettoanfangsrendite(ctx: Kontext) -> KpiWert:
    return _miete(ctx, ctx.ergebnis.nettoanfangsrendite)


def _cashflow_monat(ctx: Kontext) -> KpiWert:
    return _miete(ctx, ctx.ergebnis.cashflow_monat)


def _kaufpreisempfehlung(ctx: Kontext) -> KpiWert:
    ke = ctx.ergebnis.kaufpreisempfehlung
    return None if ke.preis is None or ke.qualitaet is None else (ke.preis, ke.qualitaet)


def _preisabstand(ctx: Kontext) -> KpiWert:
    ke = ctx.ergebnis.kaufpreisempfehlung
    return None if ke.preisabstand is None or ke.qualitaet is None else (ke.preisabstand, ke.qualitaet)


def _preis_m2(ctx: Kontext) -> KpiWert:
    return (ctx.ergebnis.annahmen.kaufpreis / ctx.flaeche, "exakt") if ctx.flaeche else None


def _mietpotenzial(ctx: Kontext) -> KpiWert:
    m = ctx.ergebnis.annahmen.miete_ist
    if not m or not ctx.marktmiete_eur_m2 or not ctx.flaeche:
        return None
    return _miete(ctx, (ctx.marktmiete_eur_m2 * ctx.flaeche * 12 - m) / m)


REGISTER: dict[str, Kpi] = {
    k.name: k
    for k in (
        Kpi("bruttorendite", "Jahresnettokaltmiete (Ist) / Kaufpreis", "Anteil", _bruttorendite),
        Kpi("faktor", "Kaufpreis / Jahresnettokaltmiete", "fach", _faktor),
        Kpi("nettoanfangsrendite", "(Miete − Bewirtschaftung) / (Kaufpreis + Nebenkosten)", "Anteil", _nettoanfangsrendite),
        Kpi("cashflow_monat", "(Miete − Bewirtschaftung − Kapitaldienst) / 12", "€/Monat", _cashflow_monat),
        Kpi("kaufpreisempfehlung", "Kaufpreis für den Ziel-Cashflow", "€", _kaufpreisempfehlung),
        Kpi("preisabstand", "(Angebotspreis − Empfehlung) / Angebotspreis; positiv = Angebot liegt darüber", "Anteil", _preisabstand),
        Kpi("preis_m2", "Kaufpreis / Wohnfläche", "€/m²", _preis_m2),
        Kpi("mietpotenzial", "(Marktmiete − Ist-Miete) / Ist-Miete", "Anteil", _mietpotenzial),
    )
}


def berechne_alle(ctx: Kontext) -> dict[str, KpiWert]:
    return {name: kpi.fn(ctx) for name, kpi in REGISTER.items()}


def normalisiere(wert: float, n: Normalize) -> float:
    """Linear auf 0–100 Punkte; min > max kehrt die Richtung um (z. B. Faktor: niedriger ist besser)."""
    if n.max == n.min:
        return 100.0 if wert >= n.max else 0.0
    punkte = (wert - n.min) / (n.max - n.min) * 100
    return max(0.0, min(100.0, punkte))


def as_json(werte: dict[str, KpiWert]) -> dict[str, Any]:
    return {k: (None if v is None else {"wert": v[0], "qualitaet": v[1]}) for k, v in werte.items()}
