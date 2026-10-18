"""Bewertung: Ausschlusskriterien (Stufe 3) → KPIs → Score → Ranking. Deterministisch, ohne Claude.

Gleiche Eingabe ergibt gleichen Score. Jede Bewertung speichert ihren Rechenweg (`kpis_json`)
und einen Hash der verwendeten Konfiguration (`config_hash`).
"""

from __future__ import annotations

import ast
import hashlib
import json
import operator
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .config import Config, ConfigError, HardFilterRule, Profile
from .db import now_iso
from .extraction import field_values, load_schema
from .finance import Qualitaet, annahmen_fuer, simulate
from .kpis import REGISTER, Kontext, KpiWert, as_json, berechne_alle, normalisiere

SCORING_VERSION = 1  # erhöhen, wenn sich die Rechenlogik ändert → config_hash ändert sich mit
LISTING_FELDER = ("preis", "flaeche", "zimmer", "baujahr", "plz", "ort", "provider", "energieklasse")
QUELLE_QUALITAET: dict[str, Qualitaet] = {"portal": "exakt", "regel": "extrahiert", "claude": "extrahiert", "schätzung": "geschätzt"}


# --------------------------------------------------------------------------- Formel (sicherer Ausdrucks-Evaluator)

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_FUNCS = {"min": min, "max": max, "abs": abs}


class FormelFehler(Exception):
    pass


def formel_namen(formel: str) -> set[str]:
    """Prüft die Syntax (nur Zahlen, Namen, + − × ÷, min/max/abs) und liefert die verwendeten Namen."""
    try:
        tree = ast.parse(formel, mode="eval")
    except SyntaxError as exc:
        raise FormelFehler(f"Formel nicht lesbar: {exc.msg}") from exc
    namen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS or node.keywords:
                raise FormelFehler("Erlaubte Funktionen: min, max, abs")
        elif isinstance(node, ast.Name):
            if node.id not in _FUNCS:
                namen.add(node.id)
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, int | float) or isinstance(node.value, bool):
                raise FormelFehler("Nur Zahlen als Konstanten erlaubt")
        elif not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Load, ast.USub, ast.UAdd, *_BINOPS)):
            raise FormelFehler(f"Nicht erlaubt in der Formel: {type(node).__name__}")
    return namen


def werte_formel(formel: str, variablen: dict[str, float]) -> float:
    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variablen:
                raise FormelFehler(f"Wert für '{node.id}' fehlt")
            return variablen[node.id]
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            try:
                return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
            except ZeroDivisionError as exc:
                raise FormelFehler("Division durch 0") from exc
        if isinstance(node, ast.Call):
            return float(_FUNCS[node.func.id](*(ev(a) for a in node.args)))  # type: ignore[union-attr]
        raise FormelFehler(f"Nicht erlaubt: {type(node).__name__}")

    formel_namen(formel)
    return ev(ast.parse(formel, mode="eval"))


# --------------------------------------------------------------------------- Prüfung der Profil-Konfiguration


def erlaubte_felder(profile: Profile) -> set[str]:
    return set(LISTING_FELDER) | set(load_schema(profile.objektart).fields) | set(REGISTER)


def pruefe_profil(profile: Profile) -> None:
    """Feldnamen in hard_filter/scoring gegen Schema und KPI-Register prüfen (sonst ConfigError)."""
    erlaubt = erlaubte_felder(profile)
    fehler = [f"hard_filter: unbekanntes Feld '{r.field}'" for r in profile.hard_filter if r.field not in erlaubt]
    fehler += [f"scoring.kpis: unbekannte KPI '{k}'" for k in profile.scoring.kpis if k not in REGISTER]
    for r in profile.hard_filter:
        if r.op in ("in", "not_in") and not isinstance(r.value, list):
            fehler.append(f"hard_filter '{r.field}': Operator {r.op} braucht eine Liste")
    if profile.scoring.formula:
        try:
            namen = formel_namen(profile.scoring.formula)
        except FormelFehler as exc:
            fehler.append(f"scoring.formula: {exc}")
        else:
            gueltig = set(REGISTER) | {f"{k}_n" for k in profile.scoring.kpis}
            fehler += [f"scoring.formula: unbekannter Name '{n}' (erlaubt: KPI-Namen, <kpi>_n für konfigurierte KPIs)"
                       for n in sorted(namen - gueltig)]
    elif not profile.scoring.kpis:
        fehler.append("scoring: weder kpis noch formula konfiguriert")
    if fehler:
        raise ConfigError(f"Profil '{profile.id}':\n  " + "\n  ".join(fehler))


def config_hash(config: Config, profile: Profile) -> str:
    relevant = {
        "version": SCORING_VERSION,
        "profil": profile.model_dump(mode="json", exclude={"name", "active", "fredy", "fetch_filter"}),
        "finance": config.finance_for(profile).model_dump(mode="json"),
        "grunderwerbsteuer": config.settings.grunderwerbsteuer,
    }
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- Bewertung eines Angebots

_OPS = {"==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt,
        "in": lambda a, b: a in b, "not_in": lambda a, b: a not in b}


@dataclass
class Bewertung:
    score: float | None
    ausgeschlossen: bool
    ausschlussgrund: str | None
    kaufpreisempfehlung: float | None
    preisabstand: float | None
    details: dict[str, Any] = field(default_factory=dict)


def _feldwert(name: str, listing: dict[str, Any], felder: dict[str, dict], kpis: dict[str, KpiWert]) -> tuple[Any, str | None]:
    """Wert + Qualität eines Feldes für Ausschlusskriterien (Angebot → Extraktion → KPI)."""
    if name in LISTING_FELDER:
        v = listing.get(name)
        return v, "exakt" if v is not None else None
    if name in felder:
        return felder[name]["wert"], QUELLE_QUALITAET[felder[name]["quelle"]]
    if name in kpis and kpis[name] is not None:
        return kpis[name]
    return None, None


def _hard_filter(rules: list[HardFilterRule], listing, felder, kpis) -> tuple[str | None, list[dict], list[str]]:
    protokoll, fehlend = [], []
    for r in rules:
        wert, qualitaet = _feldwert(r.field, listing, felder, kpis)
        eintrag = {"feld": r.field, "op": r.op, "soll": r.value, "ist": wert, "qualitaet": qualitaet}
        if wert is None:
            eintrag["ergebnis"] = "fehlt"
            protokoll.append(eintrag)
            if r.on_missing == "drop":
                return f"{r.field} fehlt", protokoll, fehlend
            fehlend.append(r.field)
            continue
        try:
            ok = _OPS[r.op](wert, r.value)
        except TypeError:
            ok = False
        eintrag["ergebnis"] = "ok" if ok else "verletzt"
        protokoll.append(eintrag)
        if not ok:
            return f"{r.field} {r.op} {r.value} verletzt (ist: {_fmt(wert)})", protokoll, fehlend
    return None, protokoll, fehlend


def _fmt(v: Any) -> str:
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def bewerte(config: Config, profile: Profile, listing: dict[str, Any], felder: dict[str, dict]) -> Bewertung:
    """Reine Funktion: dieselben Eingaben ergeben immer dieselbe Bewertung."""
    hinweise: list[str] = []
    if not listing.get("preis"):
        return Bewertung(None, False, None, None, None, {"hinweise": ["Kaufpreis fehlt – keine Bewertung"], "unvollstaendig": ["preis"]})

    miete = None
    if "jahresnettokaltmiete_ist" in felder:
        m = felder["jahresnettokaltmiete_ist"]
        miete = (float(m["wert"]), QUELLE_QUALITAET[m["quelle"]])
    provision = felder.get("provision", {}).get("wert")
    basis = annahmen_fuer(config, profile, float(listing["preis"]), listing.get("flaeche"), miete, provision)
    ergebnis = simulate(basis)
    kpis = berechne_alle(Kontext(ergebnis, listing.get("flaeche"), config.finance_for(profile).marktmiete_eur_m2))

    grund, filterprotokoll, fehlend = _hard_filter(profile.hard_filter, listing, felder, kpis)
    unvollstaendig = list(fehlend)

    # Punkte je konfigurierter KPI
    kpi_details: dict[str, dict] = {}
    summe = gewichte = 0.0
    for name, cfg in profile.scoring.kpis.items():
        wert = kpis.get(name)
        d: dict[str, Any] = {"wert": None if wert is None else wert[0], "qualitaet": None if wert is None else wert[1],
                             "gewicht": cfg.weight, "on_missing": cfg.on_missing}
        if wert is None or wert[1] == "geschätzt":
            if wert is None or cfg.on_missing != "estimate":
                unvollstaendig.append(name)
            if cfg.on_missing == "exclude":
                d["verwendet"], d["punkte"] = False, None
                kpi_details[name] = d
                continue
            if wert is None or cfg.on_missing == "zero":
                d["punkte"] = 0.0
            else:
                d["punkte"] = normalisiere(wert[0], cfg.normalize)
        else:
            d["punkte"] = normalisiere(wert[0], cfg.normalize)
        d["verwendet"] = True
        summe += cfg.weight * d["punkte"]
        gewichte += cfg.weight
        kpi_details[name] = d

    score: float | None
    if profile.scoring.formula:
        variablen = {k: v[0] for k, v in kpis.items() if v is not None}
        variablen |= {f"{k}_n": d["punkte"] for k, d in kpi_details.items() if d.get("punkte") is not None}
        try:
            score = werte_formel(profile.scoring.formula, variablen)
        except FormelFehler as exc:
            score = None
            hinweise.append(f"Formel nicht berechenbar: {exc}")
    else:
        score = summe / gewichte if gewichte > 0 else None
    if score is not None:
        score = round(score, 4)

    ke = ergebnis.kaufpreisempfehlung
    if ke.status != "ok":
        hinweise.append(ke.text)
    if ke.qualitaet == "geschätzt":
        hinweise.append("Kaufpreisempfehlung beruht auf geschätzter Miete")
    hinweise += ergebnis.hinweise

    details = {
        "kpis": kpi_details,
        "alle_kpis": as_json(kpis),
        "hard_filter": filterprotokoll,
        "unvollstaendig": sorted(set(unvollstaendig)),
        "hinweise": hinweise,
        "finanzen": ergebnis.as_dict(),
    }
    return Bewertung(score, grund is not None, grund, ke.preis, ke.preisabstand, details)


# --------------------------------------------------------------------------- DB


@dataclass
class ScoreStats:
    profile_id: str
    bewertet: int = 0
    ausgeschlossen: int = 0
    unvollstaendig: int = 0
    ohne_score: int = 0
    ausschlussgruende: dict[str, int] = field(default_factory=dict)


def run_score(conn: sqlite3.Connection, config: Config, only_profile: str | None = None) -> list[ScoreStats]:
    """Alle Angebote der Profile neu bewerten (Sekunden, ohne Claude)."""
    profiles = config.active_profiles(only_profile)
    for p in profiles:
        pruefe_profil(p)
    results = []
    ts = now_iso()
    for profile in profiles:
        stats = ScoreStats(profile.id)
        h = config_hash(config, profile)
        rows = conn.execute(
            "SELECT l.* FROM listing l JOIN listing_profile lp ON lp.listing_id = l.id WHERE lp.profile_id = ?", (profile.id,)
        ).fetchall()
        for row in rows:
            b = bewerte(config, profile, dict(row), field_values(conn, row["id"]))
            conn.execute(
                """INSERT INTO score (listing_id, profile_id, score, kpis_json, kaufpreisempfehlung, preisabstand,
                       hard_filter_result, ausschlussgrund, config_hash, scored_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (listing_id, profile_id) DO UPDATE SET score = excluded.score, kpis_json = excluded.kpis_json,
                       kaufpreisempfehlung = excluded.kaufpreisempfehlung, preisabstand = excluded.preisabstand,
                       hard_filter_result = excluded.hard_filter_result, ausschlussgrund = excluded.ausschlussgrund,
                       config_hash = excluded.config_hash, scored_at = excluded.scored_at""",
                (row["id"], profile.id, b.score, json.dumps(b.details, ensure_ascii=False, default=str), b.kaufpreisempfehlung,
                 b.preisabstand, "ausgeschlossen" if b.ausgeschlossen else "bestanden", b.ausschlussgrund, h, ts),
            )
            stats.bewertet += 1
            if b.ausgeschlossen:
                stats.ausgeschlossen += 1
                key = (b.ausschlussgrund or "").split(" ")[0]
                stats.ausschlussgruende[key] = stats.ausschlussgruende.get(key, 0) + 1
            if b.details.get("unvollstaendig"):
                stats.unvollstaendig += 1
            if b.score is None:
                stats.ohne_score += 1
        conn.commit()
        results.append(stats)
    return results


def ranking(conn: sqlite3.Connection, config: Config, profile_id: str, limit: int | None = None, ausgeschlossene: bool = False) -> list[sqlite3.Row]:
    """Aktive Angebote nach Score; abgelehnte/verworfene (Workflow) und ausgeschlossene standardmäßig ausgeblendet.

    Je Duplikatgruppe nur das am besten bewertete Angebot (dasselbe Objekt auf mehreren Portalen).
    """
    end = config.settings.workflow.end_status
    marks = ",".join("?" * len(end))
    sql = f"""SELECT l.id, l.titel, l.ort, l.preis, l.provider, l.url, l.duplicate_group, s.score, s.kaufpreisempfehlung,
                     s.preisabstand, s.hard_filter_result, s.ausschlussgrund, s.kpis_json
              FROM score s JOIN listing l ON l.id = s.listing_id
              LEFT JOIN workflow w ON w.duplicate_group = l.duplicate_group
              WHERE s.profile_id = ? AND l.status_portal = 'aktiv'
                AND (w.status IS NULL OR w.status NOT IN ({marks}))
                {"" if ausgeschlossene else "AND s.hard_filter_result = 'bestanden'"}
              ORDER BY s.score IS NULL, s.score DESC, l.id"""
    out: list[sqlite3.Row] = []
    gesehen: set[int] = set()
    for row in conn.execute(sql, [profile_id, *end]):
        gruppe = row["duplicate_group"] if row["duplicate_group"] is not None else -row["id"]
        if gruppe in gesehen:
            continue
        gesehen.add(gruppe)
        out.append(row)
        if limit and len(out) >= limit:
            break
    return out
