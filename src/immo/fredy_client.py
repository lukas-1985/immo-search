"""Zugriff auf Fredy – gekapselt, damit sich die Quelle austauschen lässt.

Zwei Varianten mit derselben Schnittstelle:
- FredyApiClient:    HTTP-API (Session-Login über /api/login)
- FredySqliteClient: Fredys SQLite-DB, nur lesend

Hinweis: Die Feldnamen der Fredy-Antworten sind noch nicht am laufenden System
geprüft (offener Punkt 1, Phase 1). `listing_from_row` liest daher sowohl
snake_case (DB-Spalten) als auch camelCase. Abweichungen hier anpassen.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Protocol

import httpx

from .config import Config, ConfigError, FredySettings, Profile, secret
from .models import FredyJob, FredyListing, parse_number


class FredyError(Exception):
    pass


class FredyClient(Protocol):
    def list_jobs(self) -> list[FredyJob]: ...

    def iter_listings(self, job: FredyJob) -> Iterator[FredyListing]: ...

    def close(self) -> None: ...


# --------------------------------------------------------------------------- Abbildung


def _get(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _images(row: Mapping[str, Any]) -> list[str]:
    raw = _get(row, "images", "image_url", "imageUrl")
    if raw is None:
        return []
    if isinstance(raw, str):
        if raw.startswith("["):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return [raw]
        else:
            return [raw]
    return [str(x if isinstance(x, str) else x.get("url", "")) for x in raw if x]


def listing_from_row(row: Mapping[str, Any], job: FredyJob | None = None) -> FredyListing:
    fredy_id = _get(row, "id")
    url = _get(row, "link", "url")
    provider = _get(row, "provider")
    if fredy_id is None or url is None or provider is None:
        raise FredyError(f"Angebot ohne id/link/provider: {dict(row)!r:.200}")
    baujahr = parse_number(_get(row, "build_year", "buildYear"))
    is_active = _get(row, "is_active", "isActive")
    return FredyListing(
        fredy_id=str(fredy_id),
        fredy_hash=_get(row, "hash"),
        provider=str(provider).lower(),
        url=str(url),
        job_id=str(_get(row, "job_id", "jobId") or (job.id if job else "")) or None,
        titel=_get(row, "title"),
        adresse=_get(row, "address"),
        lat=parse_number(_get(row, "latitude", "lat")),
        lon=parse_number(_get(row, "longitude", "lon", "lng")),
        preis=parse_number(_get(row, "price")),
        flaeche=parse_number(_get(row, "size")),
        zimmer=parse_number(_get(row, "rooms")),
        baujahr=int(baujahr) if baujahr else None,
        energieklasse=_get(row, "energy_class", "energyClass"),
        beschreibung=_get(row, "description"),
        bilder=_images(row),
        created_at=str(_get(row, "created_at", "createdAt") or "") or None,
        is_active=is_active is None or bool(is_active) and is_active not in (0, "0", "false"),
    )


# --------------------------------------------------------------------------- HTTP-API


class FredyApiClient:
    def __init__(self, settings: FredySettings, username: str, password: str, transport: httpx.BaseTransport | None = None):
        self._settings = settings
        self._http = httpx.Client(base_url=settings.base_url.rstrip("/"), timeout=settings.timeout_s, transport=transport)
        self._login(username, password)

    def _login(self, username: str, password: str) -> None:
        try:
            r = self._http.post("/api/login", json={"username": username, "password": password})
        except httpx.HTTPError as exc:
            raise FredyError(f"Fredy nicht erreichbar ({self._settings.base_url}): {exc}") from exc
        if r.status_code >= 400:
            raise FredyError(f"Fredy-Login fehlgeschlagen: HTTP {r.status_code}")

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            r = self._http.get(path, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise FredyError(f"GET {path} fehlgeschlagen: {exc}") from exc

    def list_jobs(self) -> list[FredyJob]:
        data = self._get_json("/api/jobs")
        rows = data.get("result", data) if isinstance(data, dict) else data
        return [FredyJob(id=str(j["id"]), name=str(j["name"])) for j in rows]

    def iter_listings(self, job: FredyJob) -> Iterator[FredyListing]:
        page, size = 1, self._settings.page_size
        while True:
            data = self._get_json(
                "/api/listings/table",
                {"page": page, "pageSize": size, "sortfield": "created_at", "sortdir": "desc", "jobIdFilter": job.id},
            )
            rows = data.get("result", []) if isinstance(data, dict) else data
            for row in rows:
                yield listing_from_row(row, job)
            if len(rows) < size:
                return
            page += 1

    def close(self) -> None:
        self._http.close()


# --------------------------------------------------------------------------- SQLite (read-only)


class FredySqliteClient:
    def __init__(self, path: str | Path):
        uri = Path(path).resolve().as_uri() + "?mode=ro"
        try:
            self._conn = sqlite3.connect(uri, uri=True, timeout=30)
        except sqlite3.Error as exc:
            raise FredyError(f"Fredy-DB nicht lesbar ({path}): {exc}") from exc
        self._conn.row_factory = sqlite3.Row

    def list_jobs(self) -> list[FredyJob]:
        rows = self._conn.execute("SELECT id, name FROM jobs").fetchall()
        return [FredyJob(id=str(r["id"]), name=str(r["name"])) for r in rows]

    def iter_listings(self, job: FredyJob) -> Iterator[FredyListing]:
        cur = self._conn.execute(
            "SELECT * FROM listings WHERE job_id = ? AND COALESCE(manually_deleted, 0) = 0 ORDER BY created_at DESC",
            (job.id,),
        )
        for row in cur:
            yield listing_from_row(dict(row), job)

    def close(self) -> None:
        self._conn.close()


# --------------------------------------------------------------------------- Fabrik & Job-Auflösung


def create_client(config: Config) -> FredyClient:
    fs = config.settings.fredy
    if fs.access == "sqlite":
        return FredySqliteClient(fs.sqlite_path)  # type: ignore[arg-type]
    return FredyApiClient(fs, secret("FREDY_USERNAME") or "admin", secret("FREDY_PASSWORD", required=True))  # type: ignore[arg-type]


def resolve_jobs(profile: Profile, jobs: list[FredyJob]) -> list[FredyJob]:
    """Fredy-Jobs eines Profils über Namen bzw. Präfix finden. Fehlende Namen sind ein Fehler."""
    by_name = {j.name: j for j in jobs}
    missing = [n for n in profile.fredy.jobs if n not in by_name]
    if missing:
        raise ConfigError(f"Profil '{profile.id}': Fredy-Job(s) nicht gefunden: {', '.join(missing)}")
    result = [by_name[n] for n in profile.fredy.jobs]
    if profile.fredy.job_prefix:
        result += [j for j in jobs if j.name.startswith(profile.fredy.job_prefix) and j not in result]
    return result
