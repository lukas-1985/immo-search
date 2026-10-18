"""Konfiguration: settings.yaml + Suchprofile, geprüft per Pydantic.

Eine fehlerhafte Konfiguration führt zu ConfigError und wird nie verwendet.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from ruamel.yaml import YAML

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"


class ConfigError(Exception):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- settings.yaml


class FredySettings(_Strict):
    base_url: str = "http://localhost:9998"
    access: Literal["api", "sqlite"] = "api"
    sqlite_path: str | None = None
    page_size: int = Field(200, ge=1, le=1000)
    timeout_s: float = Field(30, gt=0)

    @model_validator(mode="after")
    def _sqlite_needs_path(self) -> FredySettings:
        if self.access == "sqlite" and not self.sqlite_path:
            raise ValueError("fredy.sqlite_path ist für access: sqlite erforderlich")
        return self


class DatabaseSettings(_Strict):
    path: str = "data/immo.db"


class McpSettings(_Strict):
    enabled: bool = True
    write_tools: list[Literal["set_status", "add_note", "start_run", "reextract_listing", "send_digest_now"]] = []


class ServerSettings(_Strict):
    bind: list[str] = ["127.0.0.1"]
    port: int = Field(8710, ge=1, le=65535)
    public_base_url: str = "http://localhost:8710"
    mcp: McpSettings = McpSettings()


class ChannelSettings(_Strict):
    enabled: bool = False
    to: str | None = None


class NotifySettings(_Strict):
    telegram: ChannelSettings = ChannelSettings()
    email: ChannelSettings = ChannelSettings()


_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class RunSchedule(_Strict):
    every_hours: int = Field(3, ge=1, le=24)
    from_: str = Field("07:00", alias="from", pattern=_HHMM)
    to: str = Field("22:00", pattern=_HHMM)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DigestSchedule(_Strict):
    at: str = Field("07:30", pattern=_HHMM)


class ScheduleSettings(_Strict):
    run: RunSchedule = RunSchedule()
    digest: DigestSchedule = DigestSchedule()


class WorkflowSettings(_Strict):
    status: list[str] = ["neu", "gesichtet", "interessant", "angefragt", "besichtigt", "angebot_abgegeben", "gekauft"]
    end_status: list[str] = ["abgelehnt", "verworfen"]
    wieder_interessant_preissenkung: float | None = Field(0.10, ge=0, le=1)

    @model_validator(mode="after")
    def _unique(self) -> WorkflowSettings:
        alle = self.status + self.end_status
        if len(alle) != len(set(alle)):
            raise ValueError("workflow: Status-Werte müssen eindeutig sein")
        if not self.status:
            raise ValueError("workflow.status darf nicht leer sein")
        return self


class FinanceAssumptions(_Strict):
    """Alle Felder optional: Profil-Werte überschreiben die Defaults aus settings.yaml."""

    bundesland: str | None = None
    eigenkapital: float | None = Field(None, ge=0)
    zins: float | None = Field(None, ge=0, le=0.25)
    tilgung: float | None = Field(None, ge=0, le=0.25)
    notar_grundbuch: float | None = Field(None, ge=0, le=0.1)
    makler_default: float | None = Field(None, ge=0, le=0.1)
    bewirtschaftung_quote: float | None = Field(None, ge=0, le=1)
    instandhaltung_eur_m2_jahr: float | None = Field(None, ge=0)
    sanierung_sofort: float | None = Field(None, ge=0)
    miete_schaetzung_eur_m2: float | None = Field(None, ge=0)
    marktmiete_eur_m2: float | None = Field(None, ge=0)  # für KPI mietpotenzial (Mietspiegel/Marktmiete netto kalt)


class SteuernSettings(_Strict):
    grenzsteuersatz: float = Field(0.42, ge=0, le=0.5)
    gebaeudeanteil: float = Field(0.75, gt=0, le=1)
    afa_satz: Literal["auto"] | float = "auto"


class Settings(_Strict):
    fredy: FredySettings = FredySettings()
    database: DatabaseSettings = DatabaseSettings()
    server: ServerSettings = ServerSettings()
    notify: NotifySettings = NotifySettings()
    schedule: ScheduleSettings = ScheduleSettings()
    workflow: WorkflowSettings = WorkflowSettings()
    finance_defaults: FinanceAssumptions = FinanceAssumptions()
    grunderwerbsteuer: dict[str, float] = {}
    steuern: SteuernSettings = SteuernSettings()


# --------------------------------------------------------------------------- Profile


class FredyJobs(_Strict):
    jobs: list[str] = []
    job_prefix: str | None = None

    @model_validator(mode="after")
    def _one_of(self) -> FredyJobs:
        if not self.jobs and not self.job_prefix:
            raise ValueError("fredy: 'jobs' oder 'job_prefix' angeben")
        return self


class Range(_Strict):
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _order(self) -> Range:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) > max ({self.max})")
        return self

    def contains(self, value: float) -> bool:
        return (self.min is None or value >= self.min) and (self.max is None or value <= self.max)

    @property
    def is_set(self) -> bool:
        return self.min is not None or self.max is not None


class Umkreis(_Strict):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    km: float = Field(gt=0)


class LocationFilter(_Strict):
    plz_prefix: list[str] = []
    orte: list[str] = []
    umkreis: Umkreis | None = None
    on_missing: Literal["keep", "drop"] = "keep"

    @property
    def is_set(self) -> bool:
        return bool(self.plz_prefix or self.orte or self.umkreis)


class FetchFilter(_Strict):
    location: LocationFilter = LocationFilter()
    preis: Range = Range()
    wohnflaeche: Range = Range()
    zimmer: Range = Range()
    baujahr: Range = Range()
    providers: list[str] = []
    exclude_keywords: list[str] = []


class HardFilterRule(_Strict):
    field: str
    op: Literal["==", "!=", ">=", "<=", ">", "<", "in", "not_in"]
    value: Any
    on_missing: Literal["keep", "drop"] = "keep"


class Normalize(_Strict):
    type: Literal["linear"] = "linear"
    min: float
    max: float


class KpiConfig(_Strict):
    weight: float = Field(ge=0)
    normalize: Normalize
    on_missing: Literal["estimate", "zero", "exclude"] = "estimate"


class ScoringConfig(_Strict):
    kpis: dict[str, KpiConfig] = {}
    formula: str | None = None
    alert_threshold: float = Field(75, ge=0, le=100)
    digest_top_n: int = Field(10, ge=1)


class KaufpreisempfehlungConfig(_Strict):
    ziel_cashflow_monat: float = 0
    tilgung_einrechnen: bool = True


class Profile(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    active: bool = True
    objektart: Literal["mehrfamilienhaus", "eigentumswohnung", "wohn_geschaeftshaus"]
    fredy: FredyJobs
    fetch_filter: FetchFilter = FetchFilter()
    hard_filter: list[HardFilterRule] = []
    scoring: ScoringConfig = ScoringConfig()
    finance: FinanceAssumptions = FinanceAssumptions()
    kaufpreisempfehlung: KaufpreisempfehlungConfig = KaufpreisempfehlungConfig()


# --------------------------------------------------------------------------- Laden


class Config(BaseModel):
    settings: Settings
    profiles: dict[str, Profile]
    config_dir: Path

    def active_profiles(self, only: str | None = None) -> list[Profile]:
        if only is not None:
            if only not in self.profiles:
                raise ConfigError(f"Profil '{only}' nicht gefunden (vorhanden: {', '.join(self.profiles) or '-'})")
            return [self.profiles[only]]
        return [p for p in self.profiles.values() if p.active]

    def db_path(self) -> Path:
        p = Path(self.settings.database.path)
        return p if p.is_absolute() else self.config_dir.parent / p

    def finance_for(self, profile: Profile) -> FinanceAssumptions:
        """Defaults aus settings.yaml, überschrieben durch die gesetzten Profil-Werte."""
        merged = self.settings.finance_defaults.model_dump()
        merged.update(profile.finance.model_dump(exclude_none=True))
        return FinanceAssumptions(**merged)


def _read_yaml(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as f:
            return YAML(typ="safe").load(f)
    except Exception as exc:  # noqa: BLE001 - Parserfehler einheitlich melden
        raise ConfigError(f"{path}: YAML nicht lesbar: {exc}") from exc


def _validate(model: type[BaseModel], data: Any, path: Path) -> Any:
    try:
        return model.model_validate(data or {})
    except ValidationError as exc:
        lines = [f"  {'.'.join(str(x) for x in e['loc']) or '(Wurzel)'}: {e['msg']}" for e in exc.errors()]
        raise ConfigError(f"{path}: ungültige Konfiguration\n" + "\n".join(lines)) from exc


def load_config(config_dir: Path | str | None = None) -> Config:
    config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    load_dotenv(config_dir.parent / ".env")

    settings_path = config_dir / "settings.yaml"
    if not settings_path.exists():
        raise ConfigError(f"{settings_path} fehlt")
    settings: Settings = _validate(Settings, _read_yaml(settings_path), settings_path)

    profiles: dict[str, Profile] = {}
    for path in sorted((config_dir / "profiles").glob("*.yaml")):
        profile: Profile = _validate(Profile, _read_yaml(path), path)
        if profile.id != path.stem:
            raise ConfigError(f"{path}: id '{profile.id}' muss dem Dateinamen entsprechen")
        bl = profile.finance.bundesland
        if bl is not None and bl not in settings.grunderwerbsteuer:
            raise ConfigError(f"{path}: Bundesland '{bl}' fehlt in settings.yaml → grunderwerbsteuer")
        profiles[profile.id] = profile

    return Config(settings=settings, profiles=profiles, config_dir=config_dir)


def secret(name: str, required: bool = False) -> str | None:
    value = os.environ.get(name) or None
    if required and value is None:
        raise ConfigError(f"Umgebungsvariable {name} fehlt (in .env setzen)")
    return value
