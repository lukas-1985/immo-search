"""Eigene SQLite-DB (data/immo.db) im WAL-Modus. Fredys DB wird nie beschrieben."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA_V1 = """
CREATE TABLE listing (
    id                INTEGER PRIMARY KEY,
    fredy_id          TEXT,
    fredy_hash        TEXT,
    provider          TEXT NOT NULL,
    url               TEXT NOT NULL,
    titel             TEXT,
    adresse           TEXT,
    plz               TEXT,
    ort               TEXT,
    lat               REAL,
    lon               REAL,
    preis             REAL,
    flaeche           REAL,
    zimmer            REAL,
    baujahr           INTEGER,
    energieklasse     TEXT,
    beschreibung      TEXT,
    beschreibung_hash TEXT,
    bilder            TEXT,              -- JSON-Liste von URLs
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL,
    status_portal     TEXT NOT NULL DEFAULT 'aktiv' CHECK (status_portal IN ('aktiv', 'entfernt')),
    duplicate_group   INTEGER,
    UNIQUE (provider, url)
);
CREATE INDEX ix_listing_fredy_id ON listing (fredy_id);
CREATE INDEX ix_listing_dupgroup ON listing (duplicate_group);

CREATE TABLE listing_profile (
    listing_id   INTEGER NOT NULL REFERENCES listing (id) ON DELETE CASCADE,
    profile_id   TEXT NOT NULL,
    fredy_job_id TEXT,
    first_seen   TEXT NOT NULL,
    PRIMARY KEY (listing_id, profile_id)
);

CREATE TABLE price_history (
    listing_id INTEGER NOT NULL REFERENCES listing (id) ON DELETE CASCADE,
    datum      TEXT NOT NULL,
    preis      REAL NOT NULL
);
CREATE INDEX ix_price_history ON price_history (listing_id, datum);

CREATE TABLE extraction (
    listing_id     INTEGER NOT NULL REFERENCES listing (id) ON DELETE CASCADE,
    feld           TEXT NOT NULL,
    wert           TEXT,                 -- JSON
    quelle         TEXT NOT NULL CHECK (quelle IN ('portal', 'regel', 'claude', 'schätzung')),
    konfidenz      TEXT CHECK (konfidenz IN ('hoch', 'mittel', 'niedrig')),
    belegstelle    TEXT,
    schema_version INTEGER,
    extracted_at   TEXT NOT NULL,
    PRIMARY KEY (listing_id, feld)
);

CREATE TABLE score (
    listing_id          INTEGER NOT NULL REFERENCES listing (id) ON DELETE CASCADE,
    profile_id          TEXT NOT NULL,
    score               REAL,
    kpis_json           TEXT,
    kaufpreisempfehlung REAL,
    preisabstand        REAL,
    hard_filter_result  TEXT,
    ausschlussgrund     TEXT,
    config_hash         TEXT,
    scored_at           TEXT NOT NULL,
    PRIMARY KEY (listing_id, profile_id)
);

CREATE TABLE scenario (
    id            INTEGER PRIMARY KEY,
    listing_id    INTEGER NOT NULL REFERENCES listing (id) ON DELETE CASCADE,
    profile_id    TEXT NOT NULL,
    name          TEXT NOT NULL,
    annahmen_json TEXT NOT NULL,
    ergebnis_json TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE workflow (
    duplicate_group INTEGER PRIMARY KEY,
    status          TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    updated_by      TEXT NOT NULL CHECK (updated_by IN ('ui', 'mcp', 'system'))
);

CREATE TABLE workflow_history (
    id              INTEGER PRIMARY KEY,
    duplicate_group INTEGER NOT NULL,
    status_alt      TEXT,
    status_neu      TEXT NOT NULL,
    quelle          TEXT NOT NULL,
    notiz           TEXT,
    zeitpunkt       TEXT NOT NULL
);

CREATE TABLE note (
    id         INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES listing (id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    quelle     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE job (
    id            INTEGER PRIMARY KEY,
    typ           TEXT NOT NULL,
    parameter     TEXT,
    ausgeloest_von TEXT NOT NULL CHECK (ausgeloest_von IN ('zeitplan', 'ui', 'mcp', 'cli')),
    status        TEXT NOT NULL CHECK (status IN ('wartend', 'läuft', 'fertig', 'fehler')),
    start         TEXT,
    ende          TEXT,
    log_pfad      TEXT
);

CREATE TABLE notification (
    id         INTEGER PRIMARY KEY,
    listing_id INTEGER REFERENCES listing (id) ON DELETE CASCADE,
    profile_id TEXT,
    kanal      TEXT NOT NULL,
    anlass     TEXT NOT NULL,
    gesendet_at TEXT NOT NULL
);

CREATE TABLE run_log (
    id          INTEGER PRIMARY KEY,
    schritt     TEXT NOT NULL,
    profile_id  TEXT,
    start       TEXT NOT NULL,
    ende        TEXT,
    zahlen_json TEXT,
    fehler      TEXT
);

CREATE TABLE config_change (
    id          INTEGER PRIMARY KEY,
    datei       TEXT NOT NULL,
    diff        TEXT NOT NULL,
    backup_pfad TEXT,
    zeitpunkt   TEXT NOT NULL
);
"""

# v2: Stand der Claude-Auswertung je Angebot (für Hash-Vergleich und Wiederholungen)
SCHEMA_V2 = """
CREATE TABLE extraction_status (
    listing_id        INTEGER PRIMARY KEY REFERENCES listing (id) ON DELETE CASCADE,
    beschreibung_hash TEXT,
    schema_version    INTEGER,
    status            TEXT NOT NULL CHECK (status IN ('ok', 'fehler')),
    versuche          INTEGER NOT NULL DEFAULT 0,
    letzter_fehler    TEXT,
    updated_at        TEXT NOT NULL
);
"""

MIGRATIONS = {1: SCHEMA_V1, 2: SCHEMA_V2}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def connect(path: Path | str, check_same_thread: bool = True) -> sqlite3.Connection:
    """Öffnet die DB (legt sie samt Schema bei Bedarf an).

    `check_same_thread=False` nur, wenn eine Verbindung garantiert nicht gleichzeitig genutzt wird
    (Server: eine Verbindung je Anfrage, die FastAPI aber über Threads weiterreichen kann).
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"DB-Schema {version} ist neuer als der Code ({SCHEMA_VERSION})")
    for target in range(version + 1, SCHEMA_VERSION + 1):
        conn.executescript(f"BEGIN; {MIGRATIONS[target]} PRAGMA user_version = {target}; COMMIT;")
