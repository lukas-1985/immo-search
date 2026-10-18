"""Finanzrechnung: eine Funktion `simulate()` für Score, Kaufpreisempfehlung, Oberfläche und MCP.

Größen (siehe PLAN.md 5.6):
    M  Jahresnettokaltmiete (Ist)          B  Bewirtschaftung = quote · M + instandhaltung · Wohnfläche
    n  Kaufnebenkosten-Quote               S  Sanierung sofort      EK  Eigenkapital
    k  Kapitaldienst-Satz = Zins + Tilgung (bzw. nur Zins)          C  Ziel-Cashflow pro Monat

    Darlehen      D  = max(0, P · (1 + n) + S − EK)
    Cashflow/Jahr CF = M − B − k · D
    Empfehlung    P* = ((M − B − 12·C) / k + EK − S) / (1 + n)

Phase 8b erweitert `simulate()` um Mehrjahresverlauf, Steuern, IRR usw.; die Werte hier bleiben gleich.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

from .config import Config, ConfigError, Profile

Qualitaet = Literal["exakt", "extrahiert", "geschätzt"]
QUALITAET_RANG: dict[str, int] = {"exakt": 2, "extrahiert": 1, "geschätzt": 0}
ZINS_SPANNE = 0.005  # ± 0,5 Prozentpunkte


def schlechteste(*q: Qualitaet | None) -> Qualitaet | None:
    vorhanden = [x for x in q if x is not None]
    return min(vorhanden, key=QUALITAET_RANG.__getitem__) if vorhanden else None


@dataclass(frozen=True)
class Annahmen:
    """Alle Eingangswerte einer Rechnung. Jeder Wert lässt sich in der Simulation einzeln überschreiben."""

    kaufpreis: float
    miete_ist: float | None  # € / Jahr, netto kalt
    miete_qualitaet: Qualitaet | None
    wohnflaeche: float | None
    grunderwerbsteuer: float
    notar_grundbuch: float
    makler: float
    sanierung_sofort: float
    eigenkapital: float
    zins: float
    tilgung: float
    bewirtschaftung_quote: float
    instandhaltung_eur_m2_jahr: float
    ziel_cashflow_monat: float
    tilgung_einrechnen: bool
    makler_quelle: Literal["anzeige", "default"] = "default"
    hinweise: tuple[str, ...] = ()

    @property
    def nebenkosten_quote(self) -> float:
        return self.grunderwerbsteuer + self.notar_grundbuch + self.makler

    @property
    def kapitaldienst_satz(self) -> float:
        return self.zins + (self.tilgung if self.tilgung_einrechnen else 0.0)

    def mit(self, **aenderungen: Any) -> Annahmen:
        unbekannt = set(aenderungen) - set(self.__dataclass_fields__)
        if unbekannt:
            raise ValueError(f"Unbekannte Parameter: {', '.join(sorted(unbekannt))}")
        return replace(self, **aenderungen)


@dataclass
class Kaufpreisempfehlung:
    preis: float | None
    status: Literal["ok", "nicht_erreichbar", "unbegrenzt", "miete_fehlt"]
    qualitaet: Qualitaet | None
    zins_minus: float | None = None  # P* bei Zins − 0,5 Pp
    zins_plus: float | None = None  # P* bei Zins + 0,5 Pp
    preisabstand: float | None = None  # (Angebotspreis − P*) / Angebotspreis

    @property
    def text(self) -> str:
        return {
            "ok": "",
            "nicht_erreichbar": "Ziel-Cashflow nicht erreichbar",
            "unbegrenzt": "Ziel-Cashflow bei jedem Preis erreicht (kein Kapitaldienst)",
            "miete_fehlt": "Miete fehlt",
        }[self.status]


@dataclass
class Ergebnis:
    annahmen: Annahmen
    nebenkosten: float
    gesamtinvestition: float
    darlehen: float
    bewirtschaftung: float | None
    zins_jahr: float
    tilgung_jahr: float
    rate_monat: float
    bruttorendite: float | None
    faktor: float | None
    nettoanfangsrendite: float | None
    cashflow_jahr: float | None
    cashflow_monat: float | None
    kaufpreisempfehlung: Kaufpreisempfehlung
    hinweise: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kaufpreisempfehlung"]["text"] = self.kaufpreisempfehlung.text
        return d


def bewirtschaftung(a: Annahmen) -> float | None:
    if a.miete_ist is None:
        return None
    return a.bewirtschaftung_quote * a.miete_ist + a.instandhaltung_eur_m2_jahr * (a.wohnflaeche or 0.0)


def darlehen(a: Annahmen, preis: float | None = None) -> float:
    p = a.kaufpreis if preis is None else preis
    return max(0.0, p * (1 + a.nebenkosten_quote) + a.sanierung_sofort - a.eigenkapital)


def empfohlener_preis(a: Annahmen) -> tuple[float | None, str]:
    """Kaufpreis P*, bei dem der Cashflow genau dem Ziel entspricht (geschlossene Formel)."""
    if a.miete_ist is None:
        return None, "miete_fehlt"
    ueberschuss = a.miete_ist - bewirtschaftung(a) - 12 * a.ziel_cashflow_monat  # type: ignore[operator]
    if ueberschuss <= 0:
        return None, "nicht_erreichbar"
    k = a.kapitaldienst_satz
    if k <= 0:
        return None, "unbegrenzt"
    p = (ueberschuss / k + a.eigenkapital - a.sanierung_sofort) / (1 + a.nebenkosten_quote)
    # P* ≤ 0: selbst ohne Kaufpreis trägt die Sanierung (abzüglich EK) das Ziel nicht
    return (p, "ok") if p > 0 else (None, "nicht_erreichbar")


def kaufpreisempfehlung(a: Annahmen) -> Kaufpreisempfehlung:
    preis, status = empfohlener_preis(a)
    ke = Kaufpreisempfehlung(preis=preis, status=status, qualitaet=a.miete_qualitaet if a.miete_ist is not None else None)  # type: ignore[arg-type]
    if preis is not None:
        ke.zins_minus = empfohlener_preis(a.mit(zins=max(0.0, a.zins - ZINS_SPANNE)))[0]
        ke.zins_plus = empfohlener_preis(a.mit(zins=a.zins + ZINS_SPANNE))[0]
        ke.preisabstand = (a.kaufpreis - preis) / a.kaufpreis if a.kaufpreis else None
    return ke


def simulate(basis: Annahmen, **aenderungen: Any) -> Ergebnis:
    """Rechnet ein Angebot mit den Basis-Annahmen, optional mit geänderten Parametern."""
    a = basis.mit(**aenderungen) if aenderungen else basis
    if a.kaufpreis <= 0:
        raise ValueError("Kaufpreis muss positiv sein")
    nk = a.kaufpreis * a.nebenkosten_quote
    d = darlehen(a)
    zins_j, tilg_j = a.zins * d, a.tilgung * d
    b = bewirtschaftung(a)
    m = a.miete_ist
    cf = None if m is None else m - b - zins_j - (tilg_j if a.tilgung_einrechnen else 0.0)  # type: ignore[operator]
    return Ergebnis(
        annahmen=a,
        nebenkosten=nk,
        gesamtinvestition=a.kaufpreis + nk + a.sanierung_sofort,
        darlehen=d,
        bewirtschaftung=b,
        zins_jahr=zins_j,
        tilgung_jahr=tilg_j,
        rate_monat=(zins_j + tilg_j) / 12,
        bruttorendite=None if m is None else m / a.kaufpreis,
        faktor=None if not m else a.kaufpreis / m,
        nettoanfangsrendite=None if m is None else (m - b) / (a.kaufpreis + nk),  # type: ignore[operator]
        cashflow_jahr=cf,
        cashflow_monat=None if cf is None else cf / 12,
        kaufpreisempfehlung=kaufpreisempfehlung(a),
        hinweise=list(a.hinweise),
    )


# --------------------------------------------------------------------------- Annahmen aus Angebot + Profil

_PFLICHT = ("zins", "tilgung", "notar_grundbuch", "makler_default", "bewirtschaftung_quote")


def annahmen_fuer(
    config: Config,
    profile: Profile,
    kaufpreis: float,
    wohnflaeche: float | None,
    miete: tuple[float, Qualitaet] | None,
    provision: float | None,
) -> Annahmen:
    """Basis-Annahmen eines Angebots: Profil-Finanzannahmen, Werte aus der Anzeige, Schätzung als Rückfall."""
    f = config.finance_for(profile)
    fehlend = [n for n in _PFLICHT if getattr(f, n) is None]
    if fehlend:
        raise ConfigError(f"Profil '{profile.id}': Finanzannahme(n) fehlen: {', '.join(fehlend)} (Profil oder settings.yaml → finance_defaults)")

    hinweise = []
    if f.bundesland is None:
        grest = 0.0
        hinweise.append("Bundesland nicht gesetzt – Grunderwerbsteuer mit 0 % gerechnet")
    else:
        grest = config.settings.grunderwerbsteuer[f.bundesland]

    if miete is None and f.miete_schaetzung_eur_m2 and wohnflaeche:
        miete = (f.miete_schaetzung_eur_m2 * wohnflaeche * 12, "geschätzt")
        hinweise.append(f"Miete geschätzt: {f.miete_schaetzung_eur_m2:.2f} €/m² × {wohnflaeche:.0f} m² × 12")

    return Annahmen(
        kaufpreis=kaufpreis,
        miete_ist=miete[0] if miete else None,
        miete_qualitaet=miete[1] if miete else None,
        wohnflaeche=wohnflaeche,
        grunderwerbsteuer=grest,
        notar_grundbuch=f.notar_grundbuch,  # type: ignore[arg-type]
        makler=f.makler_default if provision is None else provision,  # type: ignore[arg-type]
        makler_quelle="default" if provision is None else "anzeige",
        sanierung_sofort=f.sanierung_sofort or 0.0,
        eigenkapital=f.eigenkapital or 0.0,
        zins=f.zins,  # type: ignore[arg-type]
        tilgung=f.tilgung,  # type: ignore[arg-type]
        bewirtschaftung_quote=f.bewirtschaftung_quote,  # type: ignore[arg-type]
        instandhaltung_eur_m2_jahr=f.instandhaltung_eur_m2_jahr or 0.0,
        ziel_cashflow_monat=profile.kaufpreisempfehlung.ziel_cashflow_monat,
        tilgung_einrechnen=profile.kaufpreisempfehlung.tilgung_einrechnen,
        hinweise=tuple(hinweise),
    )
