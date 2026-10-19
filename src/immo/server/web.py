"""Routen der Oberfläche (server-gerenderte Seiten, Jinja2). Alle Schreibaktionen per POST mit CSRF-Token."""

from __future__ import annotations

import asyncio
import json
import math
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from .. import config_edit, jobs, queries
from ..config import ConfigError, secret
from ..scoring import run_score
from ..simulation import FINANZ_FELDER, SimulationsFehler, als_yaml, simuliere_ranking
from ..workflow import WorkflowFehler, erlaubte_status, notiz_hinzufuegen, setze_status
from .auth import angemeldet, csrf_token, passwort_ok, pruefe_csrf

HIER = Path(__file__).parent
templates = Jinja2Templates(directory=str(HIER / "templates"))
router = APIRouter()


# --------------------------------------------------------------------------- Format-Helfer (Jinja-Filter)


def eur(v: Any, nachkomma: int = 0) -> str:
    if v is None:
        return "–"
    s = f"{float(v):,.{nachkomma}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def pct(v: Any, nachkomma: int = 1) -> str:
    return "–" if v is None else f"{float(v) * 100:.{nachkomma}f} %".replace(".", ",")


def zahl(v: Any, nachkomma: int = 0) -> str:
    if v is None:
        return "–"
    return f"{float(v):,.{nachkomma}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def datum(v: str | None, mit_zeit: bool = False) -> str:
    if not v:
        return "–"
    try:
        d = datetime.fromisoformat(v).astimezone()
    except ValueError:
        return v
    return d.strftime("%d.%m.%Y %H:%M" if mit_zeit else "%d.%m.%Y")


def wert_text(v: Any) -> str:
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, list):
        if v and isinstance(v[0], dict):
            return "; ".join(f"{x.get('bauteil')}{' ' + str(x['jahr']) if x.get('jahr') else ''}" for x in v)
        return "; ".join(map(str, v))
    if isinstance(v, float):
        return zahl(v, 4 if abs(v) < 1 else 0)
    return "–" if v is None else str(v)


def hervorheben(text: str | None, belege: list[str]) -> Markup:
    """Belegstellen im Anzeigentext markieren (nach Normalisierung von Leerraum)."""
    if not text:
        return Markup("")
    out = str(escape(text))
    for b in sorted({t.strip() for beleg in belege for t in beleg.split(" … ") if len(t.strip()) >= 6}, key=len, reverse=True):
        e = str(escape(b))
        if e in out:
            out = out.replace(e, f"<mark>{e}</mark>", 1)
    return Markup(out.replace("\n", "<br>"))


def preis_svg(verlauf: list[dict], empfehlung: float | None) -> Markup:
    """Preisverlauf als kleines SVG (ohne JS-Bibliothek). Gestrichelt: Kaufpreisempfehlung."""
    if not verlauf:
        return Markup("")
    w, h, pad, links = 600, 160, 34, 72
    werte = [p["preis"] for p in verlauf] + ([empfehlung] if empfehlung else [])
    lo, hi = min(werte), max(werte)
    if math.isclose(lo, hi):
        lo, hi = lo * 0.95, hi * 1.05
    zeiten = [datetime.fromisoformat(p["datum"]).timestamp() for p in verlauf]
    t0, t1 = zeiten[0], max(zeiten[-1], zeiten[0] + 86400)
    x = lambda t: links + (t - t0) / (t1 - t0) * (w - links - pad)  # noqa: E731
    y = lambda v: h - pad / 1.5 - (v - lo) / (hi - lo) * (h - pad * 1.4)  # noqa: E731
    punkte = [(x(t), y(p["preis"])) for t, p in zip(zeiten, verlauf, strict=True)]
    if len(punkte) == 1:
        punkte.append((w - pad, punkte[0][1]))
    linie = " ".join(f"{a:.1f},{b:.1f}" for a, b in punkte)
    teile = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Preisverlauf">',
             f'<polyline points="{linie}" class="chart-linie"/>']
    for a, b in punkte[: len(verlauf)]:
        teile.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3" class="chart-punkt"/>')
    if empfehlung:
        ye = y(empfehlung)
        teile.append(f'<line x1="{links}" x2="{w - pad}" y1="{ye:.1f}" y2="{ye:.1f}" class="chart-empfehlung"/>')
        teile.append(f'<text x="{w - pad}" y="{ye - 5:.1f}" text-anchor="end" class="chart-text">Empfehlung {eur(empfehlung)}</text>')
    teile.append(f'<text x="{links}" y="{h - 4}" class="chart-text">{datum(verlauf[0]["datum"])}</text>')
    teile.append(f'<text x="{w - pad}" y="{h - 4}" text-anchor="end" class="chart-text">{datum(verlauf[-1]["datum"])}</text>')
    for v in {hi, lo}:
        teile.append(f'<text x="{links - 6}" y="{y(v) + 4:.1f}" text-anchor="end" class="chart-text">{zahl(v / 1000)} T€</text>')
    teile.append("</svg>")
    return Markup("".join(teile))


templates.env.filters.update(eur=eur, pct=pct, zahl=zahl, datum=datum, wert_text=wert_text)
templates.env.globals.update(preis_svg=preis_svg, hervorheben=hervorheben)


# --------------------------------------------------------------------------- Abhängigkeiten


def zustand(request: Request):
    return request.app.state.zustand


def conn_dep(request: Request):
    yield from request.app.state.zustand.verbindung()


class Anmeldung(Exception):
    pass


def login_noetig(request: Request) -> None:
    if not angemeldet(request):
        raise HTTPException(status_code=303, headers={"Location": "/login?weiter=" + request.url.path})


def seite(request: Request, name: str, **ctx: Any) -> HTMLResponse:
    z = request.app.state.zustand
    meldung = request.session.pop("meldung", None)
    return templates.TemplateResponse(request, name, {
        "csrf": csrf_token(request), "meldung": meldung, "config": z.config,
        "profile": list(z.config.profiles.values()), "pfad": request.url.path, **ctx,
    })


def melde(request: Request, text: str, art: str = "ok") -> None:
    request.session["meldung"] = {"text": text, "art": art}


def zurueck(request: Request, ziel: str) -> RedirectResponse:
    return RedirectResponse(ziel, status_code=303)


async def formular(request: Request) -> dict[str, str]:
    form = await request.form()
    daten = {k: str(v) for k, v in form.items()}
    pruefe_csrf(request, daten.get("csrf"))
    return daten


# --------------------------------------------------------------------------- Anmeldung, Health


@router.get("/login", response_class=HTMLResponse)
def login_seite(request: Request, weiter: str = "/"):
    return seite(request, "login.html", weiter=weiter if weiter.startswith("/") else "/",
                 eingerichtet=bool(secret("UI_PASSWORD_HASH")))


@router.post("/login")
async def login(request: Request):
    daten = await formular(request)
    if passwort_ok(daten.get("passwort", ""), secret("UI_PASSWORD_HASH")):
        request.session["angemeldet"] = True
        weiter = daten.get("weiter", "/")
        return zurueck(request, weiter if weiter.startswith("/") and not weiter.startswith("//") else "/")
    await asyncio.sleep(1.0)  # Raten bremsen
    melde(request, "Passwort falsch.", "fehler")
    return zurueck(request, "/login")


@router.post("/logout")
async def logout(request: Request):
    await formular(request)
    request.session.clear()
    return zurueck(request, "/login")


@router.get("/health")
def health(z=Depends(zustand)):
    conn = z.db()
    try:
        letzter = conn.execute("SELECT schritt, start, ende, fehler FROM run_log WHERE schritt NOT IN ('health', 'backup') "
                               "ORDER BY id DESC LIMIT 1").fetchone()
        return JSONResponse({"ok": True, "angebote": conn.execute("SELECT COUNT(*) FROM listing").fetchone()[0],
                             "letzter_lauf": dict(letzter) if letzter else None})
    finally:
        conn.close()


# --------------------------------------------------------------------------- Lesen


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
def start(request: Request, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    return seite(request, "uebersicht.html", u=queries.uebersicht(conn, z.config), jobs_=jobs.liste(conn, 5))


def _float(v: str | None) -> float | None:
    if v is None or v.strip() == "":
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


@router.get("/angebote", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
def angebote(request: Request, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    p = request.query_params
    filter_ = dict(
        profil=p.get("profil") or None, status=p.get("status") or None, ort=p.get("ort") or None,
        portal=p.get("portal") or None, q=p.get("q") or None,
        score_min=_float(p.get("score_min")), rendite_min=_float(p.get("rendite_min")) and _float(p.get("rendite_min")) / 100,
        preis_max=_float(p.get("preis_max")),
        nur_unvollstaendig=p.get("unvollstaendig") == "1", ausgeschlossene=p.get("ausgeschlossene") == "1",
        entfernte=p.get("entfernte") == "1",
    )
    sortierung = p.get("sort") or "score"
    absteigend = p.get("dir", "desc") != "asc"
    try:
        seite_nr = int(p.get("seite") or 1)
    except ValueError:
        seite_nr = 1
    erg = queries.liste(conn, z.config, sortierung=sortierung, absteigend=absteigend, seite=seite_nr, **filter_)
    basis = {k: v for k, v in p.items() if k not in ("seite",) and v}

    def link(**aenderung: Any) -> str:
        q = {**basis, **{k: v for k, v in aenderung.items() if v is not None}}
        return "/angebote?" + urlencode(q)

    def sortlink(feld: str) -> str:
        neu_dir = "asc" if sortierung == feld and absteigend else "desc"
        return link(sort=feld, dir=neu_dir, seite=None)

    return seite(request, "liste.html", erg=erg, p=p, link=link, sortlink=sortlink, sortierung=sortierung,
                 absteigend=absteigend, status_werte=erlaubte_status(z.config),
                 portale=[r[0] for r in conn.execute("SELECT DISTINCT provider FROM listing ORDER BY 1")])


@router.get("/angebot/{listing_id}", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
def angebot(request: Request, listing_id: int, profil: str | None = None, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    d = queries.detail(conn, z.config, listing_id)
    if d is None:
        raise HTTPException(404, "Angebot nicht gefunden")
    profile = list(d["bewertungen"])
    aktiv = profil if profil in d["bewertungen"] else (profile[0] if profile else None)
    b = d["bewertungen"].get(aktiv) if aktiv else None
    belege = [m["belegstelle"] for m in d["merkmale"].values() if m.get("belegstelle")]
    offene_jobs = conn.execute(
        "SELECT id, status FROM job WHERE typ = 'neu_auswerten' AND parameter = ? AND status IN ('wartend', 'läuft')",
        (json.dumps({"listing_id": listing_id}),)).fetchone()
    return seite(request, "detail.html", d=d, b=b, aktiv=aktiv, belege=belege, status_werte=erlaubte_status(z.config),
                 offener_job=dict(offene_jobs) if offene_jobs else None)


# --------------------------------------------------------------------------- Aktionen am Angebot


@router.post("/angebot/{listing_id}/status", dependencies=[Depends(login_noetig)])
async def status_setzen(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    daten = await formular(request)
    try:
        r = setze_status(conn, z.config, listing_id, daten.get("status", ""), "ui", daten.get("notiz"))
        melde(request, f"Status: {r['status_alt']} → {r['status']}")
    except WorkflowFehler as exc:
        melde(request, str(exc), "fehler")
    return zurueck(request, f"/angebot/{listing_id}")


@router.post("/angebot/{listing_id}/notiz", dependencies=[Depends(login_noetig)])
async def notiz(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(conn_dep)):
    daten = await formular(request)
    try:
        notiz_hinzufuegen(conn, listing_id, daten.get("text", ""), "ui")
        melde(request, "Notiz gespeichert.")
    except WorkflowFehler as exc:
        melde(request, str(exc), "fehler")
    return zurueck(request, f"/angebot/{listing_id}#notizen")


@router.post("/angebot/{listing_id}/neu-auswerten", dependencies=[Depends(login_noetig)])
async def neu_auswerten(request: Request, listing_id: int, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    await formular(request)
    try:
        job_id = jobs.einreihen(conn, z.config, "neu_auswerten", {"listing_id": listing_id}, "ui")
        melde(request, f"Neu-Auswertung eingereiht (Job {job_id}).")
    except jobs.JobFehler as exc:
        melde(request, str(exc), "fehler")
    return zurueck(request, f"/angebot/{listing_id}")


# --------------------------------------------------------------------------- Läufe


@router.get("/laeufe", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
def laeufe(request: Request, conn: sqlite3.Connection = Depends(conn_dep)):
    run_log = [dict(r) for r in conn.execute("SELECT * FROM run_log ORDER BY id DESC LIMIT 30")]
    for r in run_log:
        r["zahlen"] = json.loads(r["zahlen_json"]) if r["zahlen_json"] else {}
    return seite(request, "laeufe.html", jobs_=jobs.liste(conn, 40), run_log=run_log)


@router.post("/laeufe/starten", dependencies=[Depends(login_noetig)])
async def lauf_starten(request: Request, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    daten = await formular(request)
    typ = daten.get("typ", "lauf")
    if typ not in ("lauf", "bewerten"):
        raise HTTPException(400, "unbekannter Job-Typ")
    try:
        job_id = jobs.einreihen(conn, z.config, typ, {"profil": daten.get("profil") or None}, "ui")
        melde(request, f"Job {job_id} eingereiht.")
    except jobs.JobFehler as exc:
        melde(request, str(exc), "fehler")
    return zurueck(request, "/laeufe")


@router.get("/laeufe/{job_id}/log", response_class=PlainTextResponse, dependencies=[Depends(login_noetig)])
def job_log(job_id: int, conn: sqlite3.Connection = Depends(conn_dep)):
    text = jobs.log_text(conn, job_id)
    if text is None:
        raise HTTPException(404, "Kein Log vorhanden")
    return text


# --------------------------------------------------------------------------- Ranking-Simulation


def _aenderungen_aus_formular(daten: dict[str, str], profil, finanzen) -> dict[str, Any]:
    """Nur echte Änderungen: Finanzwerte gegen die wirksamen Werte (Standard + Profil) vergleichen."""
    ae: dict[str, Any] = {"gewichte": {}, "normalisierung": {}, "ausschluss": {}, "finanzen": {}}
    for kpi, cfg in profil.scoring.kpis.items():
        w = _float(daten.get(f"gew_{kpi}"))
        if w is not None and w != cfg.weight:
            ae["gewichte"][kpi] = w
        for k in ("min", "max"):
            v = _float(daten.get(f"n{k}_{kpi}"))
            if v is not None and v != getattr(cfg.normalize, k):
                ae["normalisierung"].setdefault(kpi, {})[k] = v
    for i, r in enumerate(profil.hard_filter):
        v = daten.get(f"hf_{i}")
        if v is not None and v.strip() != "" and v.strip().lower() != str(r.value).lower():
            ae["ausschluss"][i] = v.strip()
    for feld in FINANZ_FELDER:
        v = daten.get(f"fin_{feld}")
        if v is None or v.strip() == "":
            continue
        v = v.strip()
        wert: Any = v if feld in ("bundesland",) or (feld == "eigenkapital" and v == "nebenkosten") else _float(v)
        if wert is not None and wert != getattr(finanzen, feld):
            ae["finanzen"][feld] = wert
    ziel = _float(daten.get("ziel_cashflow_monat"))
    if ziel is not None and ziel != profil.kaufpreisempfehlung.ziel_cashflow_monat:
        ae["ziel_cashflow_monat"] = ziel
    tilg = daten.get("tilgung_einrechnen") == "1"
    if tilg != profil.kaufpreisempfehlung.tilgung_einrechnen:
        ae["tilgung_einrechnen"] = tilg
    return {k: v for k, v in ae.items() if v not in ({}, None)}


@router.get("/simulation", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
def simulation(request: Request, profil: str | None = None, z=Depends(zustand)):
    pid = queries.standard_profil(z.config, profil)
    if pid is None:
        raise HTTPException(404, "Kein Profil")
    profil_ = z.config.profiles[pid]
    return seite(request, "simulation.html", profil=profil_, finanzen=z.config.finance_for(profil_),
                 werte={}, ergebnis=None, fehler=None, finanz_felder=FINANZ_FELDER,
                 tilgung_an=profil_.kaufpreisempfehlung.tilgung_einrechnen)


@router.post("/simulation", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
async def simulation_rechnen(request: Request, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    daten = await formular(request)
    pid = queries.standard_profil(z.config, daten.get("profil"))
    profil = z.config.profiles[pid]
    ae = _aenderungen_aus_formular(daten, profil, z.config.finance_for(profil))
    ergebnis, fehler = None, None
    try:
        ergebnis = simuliere_ranking(conn, z.config, pid, ae)
    except (SimulationsFehler, ConfigError) as exc:
        fehler = str(exc)
    if daten.get("aktion") == "uebernehmen" and ergebnis is not None:
        rel, text = als_yaml(z.config, pid, ae)
        alt = config_edit.lesen(z.config.config_dir, rel)
        return seite(request, "konfig_pruefen.html", datei=rel, text=text, diff=config_edit.diff(alt, text, rel),
                     fehler=config_edit.pruefe(z.config.config_dir, {rel: text}), herkunft="Ranking-Simulation")
    return seite(request, "simulation.html", profil=profil, finanzen=z.config.finance_for(profil), werte=daten,
                 ergebnis=ergebnis, fehler=fehler, aenderungen=ae, finanz_felder=FINANZ_FELDER,
                 tilgung_an=daten.get("tilgung_einrechnen") == "1")


# --------------------------------------------------------------------------- Konfiguration


def _nach_aenderung(request: Request, conn: sqlite3.Connection, z) -> str:
    """Konfiguration neu laden und alle Profile neu bewerten (Sekunden, ohne Claude)."""
    t = time.monotonic()
    cfg = z.neu_laden()
    stats = run_score(conn, cfg)
    return f"{sum(s.bewertet for s in stats)} Angebote neu bewertet ({time.monotonic() - t:.1f} s)."


@router.get("/konfiguration", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
def konfiguration(request: Request, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    aenderungen = [dict(r) for r in conn.execute("SELECT id, datei, zeitpunkt, backup_pfad FROM config_change ORDER BY id DESC LIMIT 20")]
    return seite(request, "konfiguration.html", dateien=config_edit.dateien(z.config.config_dir),
                 backups=config_edit.backups(z.config.config_dir)[:30], aenderungen=aenderungen)


@router.get("/konfiguration/bearbeiten", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
def konfig_bearbeiten(request: Request, datei: str, z=Depends(zustand)):
    try:
        rel = config_edit.pruefe_pfad(datei)
    except config_edit.EditFehler as exc:
        raise HTTPException(400, str(exc)) from exc
    return seite(request, "konfig_bearbeiten.html", datei=rel, text=config_edit.lesen(z.config.config_dir, rel))


@router.post("/konfiguration/pruefen", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
async def konfig_pruefen(request: Request, z=Depends(zustand)):
    daten = await formular(request)
    try:
        rel = config_edit.pruefe_pfad(daten.get("datei", ""))
    except config_edit.EditFehler as exc:
        raise HTTPException(400, str(exc)) from exc
    text = daten.get("text", "").replace("\r\n", "\n")
    alt = config_edit.lesen(z.config.config_dir, rel)
    return seite(request, "konfig_pruefen.html", datei=rel, text=text, diff=config_edit.diff(alt, text, rel),
                 fehler=config_edit.pruefe(z.config.config_dir, {rel: text}), herkunft=None)


@router.post("/konfiguration/speichern", dependencies=[Depends(login_noetig)])
async def konfig_speichern(request: Request, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    daten = await formular(request)
    try:
        r = config_edit.speichern(conn, z.config.config_dir, daten.get("datei", ""), daten.get("text", ""))
    except config_edit.EditFehler as exc:
        melde(request, f"Nicht gespeichert: {exc}", "fehler")
        return zurueck(request, "/konfiguration")
    if not r["geaendert"]:
        melde(request, "Keine Änderung.")
    else:
        melde(request, f"Gespeichert (Backup angelegt). {_nach_aenderung(request, conn, z)}")
    return zurueck(request, "/konfiguration")


@router.post("/konfiguration/profil/{profil_id}/aktiv", dependencies=[Depends(login_noetig)])
async def profil_aktiv(request: Request, profil_id: str, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    daten = await formular(request)
    try:
        config_edit.profil_aktiv(conn, z.config.config_dir, profil_id, daten.get("aktiv") == "1")
        melde(request, f"Profil {profil_id} {'aktiviert' if daten.get('aktiv') == '1' else 'deaktiviert'}. {_nach_aenderung(request, conn, z)}")
    except config_edit.EditFehler as exc:
        melde(request, str(exc), "fehler")
    return zurueck(request, "/konfiguration")


@router.post("/konfiguration/profil/{profil_id}/kopieren", dependencies=[Depends(login_noetig)])
async def profil_kopieren(request: Request, profil_id: str, conn: sqlite3.Connection = Depends(conn_dep), z=Depends(zustand)):
    daten = await formular(request)
    try:
        neue = daten.get("neue_id", "").strip()
        config_edit.profil_kopieren(conn, z.config.config_dir, profil_id, neue, daten.get("name") or None)
        z.neu_laden()
        melde(request, f"Profil {neue} angelegt (inaktiv). Bitte Jobs/Filter anpassen und aktivieren.")
        return zurueck(request, f"/konfiguration/bearbeiten?datei=profiles/{neue}.yaml")
    except config_edit.EditFehler as exc:
        melde(request, str(exc), "fehler")
        return zurueck(request, "/konfiguration")


@router.get("/konfiguration/backup/{name}", response_class=HTMLResponse, dependencies=[Depends(login_noetig)])
def backup_ansehen(request: Request, name: str, z=Depends(zustand)):
    try:
        rel, text = config_edit.backup_lesen(z.config.config_dir, name)
    except config_edit.EditFehler as exc:
        raise HTTPException(404, str(exc)) from exc
    aktuell = config_edit.lesen(z.config.config_dir, rel)
    return seite(request, "konfig_pruefen.html", datei=rel, text=text, diff=config_edit.diff(aktuell, text, rel),
                 fehler=config_edit.pruefe(z.config.config_dir, {rel: text}), herkunft=f"Backup {name} wiederherstellen")


@router.get("/konfiguration/aenderung/{change_id}", response_class=PlainTextResponse, dependencies=[Depends(login_noetig)])
def aenderung_ansehen(change_id: int, conn: sqlite3.Connection = Depends(conn_dep)):
    r = conn.execute("SELECT diff FROM config_change WHERE id = ?", (change_id,)).fetchone()
    if r is None:
        raise HTTPException(404)
    return r["diff"] or "(kein Unterschied)"


@router.get("/favicon.ico")
def favicon():
    return Response(status_code=204)
