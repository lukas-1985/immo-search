"""Gemeinsame Teile der CLI-Skripte unter scripts/."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import Config, ConfigError, load_config
from .db import connect


def parser(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--config-dir", help="Pfad zum config-Ordner (Standard: config/)")
    ap.add_argument("--db", help="Pfad zur DB (Standard: aus settings.yaml)")
    return ap


def open_context(args: argparse.Namespace) -> tuple[Config, sqlite3.Connection]:
    config = load_config(args.config_dir)
    return config, connect(Path(args.db) if args.db else config.db_path())


def print_json(data: Any) -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def run(main: Callable[[], int], *errors: type[Exception]) -> None:
    """Bekannte Fehler als kurze Meldung (Exit 1) statt Traceback."""
    try:
        sys.exit(main())
    except (ConfigError, *errors) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        sys.exit(1)
