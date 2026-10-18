"""MCP-Server (Streamable HTTP unter /mcp): Lese-Werkzeuge immer, Schreib-Werkzeuge einzeln freischaltbar.

Bewusst nicht über MCP: Konfiguration ändern, extrahierte Werte überschreiben, Szenarien speichern, Daten löschen.
Ausgaben sind kompakt (gerundete Zahlen, begrenzte Listen) und enthalten Links zur Detailansicht.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from mcp.server.mcpserver import MCPServer

from .. import jobs, queries
from ..kpis import REGISTER
from ..simulation import FINANZ_FELDER, simuliere_ranking
from ..workflow import erlaubte_status, notiz_hinzufuegen, setze_status

SCHREIB_WERKZEUGE = ("set_status", "add_note", "start_run", "reextract_listing")
MAX_LIMIT = 50


def _r(v: Any, n: int = 0) -> Any:
    if isinstance(v, float):
        return round(v, n) if n else round(v)
    return v


class Werkzeuge:
    """Die eigentliche Logik der Werkzeuge (ohne MCP, direkt testbar)."""

    def __init__(self, zustand):
        self.z = zustand

    @property
    def config(self):
        return self.z.config

    def _link(self, listing_id: int) -> str:
        return f"{self.config.settings.server.public_base_url.rstrip('/')}/angebot/{listing_id}"

    def _kurz(self, i: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": i["id"], "titel": i["titel"], "ort": f"{i['plz'] or ''} {i['ort'] or ''}".strip(),
            "preis": _r(i["preis"]), "wohnflaeche": _r(i["flaeche"]), "score": _r(i["score"], 1),
            "bruttorendite": _r(i["bruttorendite"], 4), "rendite_qualitaet": i["rendite_qualitaet"],
            "kaufpreisempfehlung": _r(i["kaufpreisempfehlung"]), "preisabstand": _r(i["preisabstand"], 3),
            "wohneinheiten": i["einheiten"], "portale": [p["portal"] for p in i["portale"]], "status": i["status"],
            "standzeit_tage": i["standzeit_tage"], "unvollstaendig": i["unvollstaendig"] or None,
            "ausgeschlossen": i["ausschlussgrund"] if i["ausgeschlossen"] else None, "link": self._link(i["id"]),
        }

    # ------------------------------------------------------------------ Lesen

    def list_profiles(self) -> dict[str, Any]:
        out = []
        for p in self.config.profiles.values():
            ff = p.fetch_filter
            out.append({
                "id": p.id, "name": p.name, "aktiv": p.active, "objektart": p.objektart,
                "ort": {"plz": ff.location.plz_prefix, "orte": ff.location.orte,
                        "umkreis": ff.location.umkreis.model_dump() if ff.location.umkreis else None},
                "preis": ff.preis.model_dump(), "ausschluss": [f"{r.field} {r.op} {r.value}" for r in p.hard_filter],
                "kpis": {k: {"gewicht": c.weight, "min": c.normalize.min, "max": c.normalize.max} for k, c in p.scoring.kpis.items()},
                "finanzen": self.config.finance_for(p).model_dump(exclude_none=True),
            })
        return {"profile": out}

    def search_listings(self, profil: str | None = None, score_min: float | None = None, rendite_min: float | None = None,
                        preis_max: float | None = None, preisabstand_max: float | None = None, ort: str | None = None,
                        status: str | None = None, portal: str | None = None, seit: str | None = None,
                        volltext: str | None = None, sortierung: str = "score", absteigend: bool = True,
                        ausgeschlossene: bool = False, limit: int = 20) -> dict[str, Any]:
        conn = self.z.db()
        try:
            erg = queries.liste(conn, self.config, profil=profil, score_min=score_min, rendite_min=rendite_min,
                                preis_max=preis_max, preisabstand_max=preisabstand_max, ort=ort, status=status,
                                portal=portal, seit=seit, q=volltext, sortierung=sortierung, absteigend=absteigend,
                                ausgeschlossene=ausgeschlossene, pro_seite=max(1, min(limit, MAX_LIMIT)))
        finally:
            conn.close()
        return {"profil": erg["profil"], "treffer_gesamt": erg["gesamt"], "angebote": [self._kurz(i) for i in erg["items"]]}

    def get_top_listings(self, profil: str | None = None, n: int = 10) -> dict[str, Any]:
        return self.search_listings(profil=profil, limit=n)

    def get_listing(self, listing_id: int, profil: str | None = None, mit_text: bool = True) -> dict[str, Any]:
        conn = self.z.db()
        try:
            d = queries.detail(conn, self.config, listing_id)
        finally:
            conn.close()
        if d is None:
            return {"fehler": f"Angebot {listing_id} nicht gefunden"}
        l = d["listing"]
        pid = profil if profil in d["bewertungen"] else next(iter(d["bewertungen"]), None)
        b = d["bewertungen"].get(pid) if pid else None
        out: dict[str, Any] = {
            "id": l["id"], "titel": l["titel"], "adresse": l["adresse"], "plz": l["plz"], "ort": l["ort"],
            "preis": _r(l["preis"]), "wohnflaeche": _r(l["flaeche"]), "zimmer": l["zimmer"], "baujahr": l["baujahr"],
            "portale": d["portale"], "status": d["status"], "standzeit_tage": d["standzeit_tage"], "link": self._link(l["id"]),
            "preisverlauf": d["preisverlauf"],
            "merkmale": {k: {kk: v.get(kk) for kk in ("wert", "quelle", "konfidenz", "belegstelle", "rechenweg") if v.get(kk) is not None}
                         for k, v in d["merkmale"].items()},
            "notizen": d["notizen"][:10], "status_verlauf": d["status_verlauf"][:10],
        }
        if b:
            f = b["details"].get("finanzen", {})
            out["bewertung"] = {
                "profil": pid, "score": _r(b["score"], 1), "ausgeschlossen": b["ausschlussgrund"],
                "kaufpreisempfehlung": f.get("kaufpreisempfehlung"), "preisabstand": _r(b["preisabstand"], 3),
                "finanzen": {k: _r(v, 2) for k, v in f.items() if k not in ("annahmen", "kaufpreisempfehlung", "hinweise")},
                "annahmen": f.get("annahmen"), "hinweise": b["details"].get("hinweise"),
            }
        if mit_text and d["beschreibung"]:
            out["beschreibung"] = d["beschreibung"][:4000] + (" …(gekürzt)" if len(d["beschreibung"]) > 4000 else "")
        return out

    def explain_score(self, listing_id: int, profil: str | None = None) -> dict[str, Any]:
        conn = self.z.db()
        try:
            d = queries.detail(conn, self.config, listing_id)
        finally:
            conn.close()
        if d is None or not d["bewertungen"]:
            return {"fehler": f"Angebot {listing_id} nicht gefunden oder nicht bewertet"}
        pid = profil if profil in d["bewertungen"] else next(iter(d["bewertungen"]))
        b = d["bewertungen"][pid]
        p = self.config.profiles.get(pid)
        return {
            "id": listing_id, "profil": pid, "score": _r(b["score"], 2), "formel": p.scoring.formula if p else None,
            "methode": "gewichteter Mittelwert der normalisierten KPIs (0–100)" if p and not p.scoring.formula else "Formel",
            "kpis": b["details"].get("kpis"), "ausschlusskriterien": b["details"].get("hard_filter"),
            "ausgeschlossen": b["ausschlussgrund"], "unvollstaendig_oder_geschaetzt": b["details"].get("unvollstaendig"),
            "hinweise": b["details"].get("hinweise"), "link": self._link(listing_id),
        }

    def compare_listings(self, listing_ids: list[int], profil: str | None = None) -> dict[str, Any]:
        if not 2 <= len(listing_ids) <= 5:
            return {"fehler": "2 bis 5 Angebote angeben"}
        return {"angebote": [self.get_listing(i, profil, mit_text=False) for i in listing_ids]}

    def get_changes(self, seit: str | None = None, tage: int | None = 7) -> dict[str, Any]:
        if not seit:
            seit = (datetime.now(UTC) - timedelta(days=tage or 7)).isoformat()
        conn = self.z.db()
        try:
            a = queries.aenderungen(conn, seit)
        finally:
            conn.close()
        for liste_ in a.values():
            if isinstance(liste_, list):
                for x in liste_:
                    x["link"] = self._link(x["id"])
        return {k: (v[:MAX_LIMIT] if isinstance(v, list) else v) for k, v in a.items()}

    def get_stats(self) -> dict[str, Any]:
        conn = self.z.db()
        try:
            return queries.statistik(conn, self.config)
        finally:
            conn.close()

    def simulate_scoring(self, profil: str | None = None, gewichte: dict[str, float] | None = None,
                         normalisierung: dict[str, dict[str, float]] | None = None, ausschluss: dict[str, Any] | None = None,
                         finanzen: dict[str, Any] | None = None, ziel_cashflow_monat: float | None = None,
                         tilgung_einrechnen: bool | None = None, limit: int = 20) -> dict[str, Any]:
        pid = queries.standard_profil(self.config, profil)
        ae = {k: v for k, v in {"gewichte": gewichte, "normalisierung": normalisierung,
                                "ausschluss": {int(k): v for k, v in (ausschluss or {}).items()} or None,
                                "finanzen": finanzen, "ziel_cashflow_monat": ziel_cashflow_monat,
                                "tilgung_einrechnen": tilgung_einrechnen}.items() if v is not None}
        conn = self.z.db()
        try:
            erg = simuliere_ranking(conn, self.config, pid, ae, limit=max(1, min(limit, MAX_LIMIT)))
        except ValueError as exc:
            return {"fehler": str(exc)}
        finally:
            conn.close()
        for r in erg["ranking"]:
            for k in ("score_neu", "score_alt"):
                r[k] = _r(r[k], 1)
            for k in ("kpe_neu", "kpe_alt", "preis"):
                r[k] = _r(r[k])
            r["preisabstand_neu"] = _r(r["preisabstand_neu"], 3)
            r["link"] = self._link(r["id"])
        erg["hinweis"] = "Nur simuliert, nichts gespeichert. Übernahme ins Profil nur über die Oberfläche (Simulation → Als Profil übernehmen)."
        return erg

    def get_jobs(self, limit: int = 10) -> dict[str, Any]:
        conn = self.z.db()
        try:
            return {"jobs": jobs.liste(conn, max(1, min(limit, MAX_LIMIT)))}
        finally:
            conn.close()

    def felder(self) -> dict[str, Any]:
        from ..extraction import load_schema

        out: dict[str, Any] = {
            "status_werte": erlaubte_status(self.config), "end_status": self.config.settings.workflow.end_status,
            "kpis": {k.name: {"formel": k.beschreibung, "einheit": k.einheit} for k in REGISTER.values()},
            "finanzannahmen": list(FINANZ_FELDER),
            "qualitaet": "exakt (Portal) > extrahiert (Regel/Claude) > geschätzt (Annahme, z. B. Miete aus €/m²)",
            "preisabstand": "(Angebotspreis − Kaufpreisempfehlung) / Angebotspreis; negativ = Angebot liegt unter der Empfehlung",
            "kaufpreisempfehlung": "Kaufpreis, bei dem der Cashflow genau dem Ziel-Cashflow des Profils entspricht",
        }
        for objektart in {p.objektart for p in self.config.profiles.values()}:
            schema = load_schema(objektart)
            out[f"merkmale_{objektart}"] = {k: v.get("description", "") for k, v in schema.raw["properties"]["felder"]["properties"].items()}
        return out

    # ------------------------------------------------------------------ Schreiben (Quelle „mcp“)

    def set_status(self, listing_id: int, status: str, notiz: str | None = None) -> dict[str, Any]:
        conn = self.z.db()
        try:
            return setze_status(conn, self.config, listing_id, status, "mcp", notiz)
        except ValueError as exc:
            return {"fehler": str(exc)}
        finally:
            conn.close()

    def add_note(self, listing_id: int, text: str) -> dict[str, Any]:
        conn = self.z.db()
        try:
            return notiz_hinzufuegen(conn, listing_id, text, "mcp")
        except ValueError as exc:
            return {"fehler": str(exc)}
        finally:
            conn.close()

    def start_run(self, profil: str | None = None) -> dict[str, Any]:
        conn = self.z.db()
        try:
            return {"job_id": jobs.einreihen(conn, self.config, "lauf", {"profil": profil}, "mcp"),
                    "hinweis": "Lauf eingereiht; Status mit get_jobs abfragen."}
        except ValueError as exc:
            return {"fehler": str(exc)}
        finally:
            conn.close()

    def reextract_listing(self, listing_id: int) -> dict[str, Any]:
        conn = self.z.db()
        try:
            return {"job_id": jobs.einreihen(conn, self.config, "neu_auswerten", {"listing_id": listing_id}, "mcp")}
        except ValueError as exc:
            return {"fehler": str(exc)}
        finally:
            conn.close()


BESCHREIBUNGEN = {
    "list_profiles": "Suchprofile mit Kriterien (Ort, Preis, Ausschlusskriterien, KPI-Gewichte, Finanzannahmen).",
    "search_listings": "Angebote suchen und filtern (Profil, Score, Mindestrendite als Anteil z. B. 0.06, Höchstpreis, "
                       "Preisabstand, Ort/PLZ, Status, Portal, neu seit ISO-Datum, Volltext). Sortierung: score, preis, "
                       "preisabstand, bruttorendite, standzeit, neu, einheiten. Je Objekt eine Zeile (Duplikate zusammengefasst).",
    "get_top_listings": "Die n besten Angebote eines Profils nach Score.",
    "get_listing": "Alle Daten eines Angebots: Stammdaten, Merkmale mit Belegstelle, Bewertung, Kaufpreisempfehlung mit Annahmen, "
                   "Preisverlauf, Status, Notizen, Anzeigentext.",
    "explain_score": "Warum hat ein Angebot diesen Score? KPIs mit Punkten und Gewicht, Ausschlusskriterien, Schätzungen.",
    "compare_listings": "2–5 Angebote nebeneinander (ohne Anzeigentext).",
    "get_changes": "Neue Angebote, Preisänderungen und entfernte Angebote seit einem Zeitpunkt (ISO) oder den letzten n Tagen.",
    "get_stats": "Bestand je Portal, Score-Verteilung und Ausschlussgründe je Profil.",
    "simulate_scoring": "Ranking mit geänderten KPI-Gewichten, Normalisierungsgrenzen, Ausschluss-Schwellen (Index → Wert) oder "
                        "Finanzannahmen neu rechnen, OHNE zu speichern. Zeigt Auf- und Absteiger.",
    "get_jobs": "Status laufender und letzter Läufe.",
    "set_status": "Bearbeitungsstatus eines Angebots setzen (gilt für alle Portale desselben Objekts), optional mit Notiz.",
    "add_note": "Notiz zu einem Angebot hinzufügen.",
    "start_run": "Kompletten Lauf anstoßen (Sync, Regeln, Claude-Extraktion, Bewertung), optional nur ein Profil.",
    "reextract_listing": "Ein Angebot von Claude neu auswerten lassen (danach neu bewerten).",
}


def baue_mcp(zustand) -> MCPServer:
    w = Werkzeuge(zustand)
    mcp = MCPServer(
        name="immo-search",
        instructions="Persönliche Immobilien-Suche (Kapitalanlage). Zahlen: Euro, Anteile als Dezimalzahl (0.06 = 6 %). "
                     "Score 0–100. Lies die Ressource immo://felder, wenn Begriffe unklar sind. Links führen zur Weboberfläche.",
    )
    for name in ("list_profiles", "search_listings", "get_top_listings", "get_listing", "explain_score", "compare_listings",
                 "get_changes", "get_stats", "simulate_scoring", "get_jobs"):
        mcp.tool(name=name, description=BESCHREIBUNGEN[name])(getattr(w, name))
    freigegeben = set(zustand.config.settings.server.mcp.write_tools)
    for name in SCHREIB_WERKZEUGE:
        if name in freigegeben:
            mcp.tool(name=name, description=BESCHREIBUNGEN[name])(getattr(w, name))

    @mcp.resource("immo://felder", name="felder", description="Felder, KPIs, Status-Werte und Begriffe der Immo-Suche",
                  mime_type="application/json")
    def felder() -> dict[str, Any]:
        return w.felder()

    return mcp
