"""CLI: Backup von data/immo.db, config/ und Fredys DB-Ordner anlegen, alte Backups aufräumen.

    python scripts/backup.py [--ziel <ordner>]

Ziel, Aufbewahrungsfrist und Fredys Ordner stehen in settings.yaml → backup. Ergebnis in run_log
(Schritt `backup`). Exit-Code 0 ok, 1 Fehler, 2 mit Warnungen (z. B. Fredys Ordner fehlt).
"""

from __future__ import annotations

import json
from pathlib import Path

from immo.backup import BackupFehler, erstelle_backup
from immo.cli import open_context, parser, print_json, run
from immo.db import now_iso


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--ziel", help="statt settings.yaml → backup.ziel")
    args = ap.parse_args()

    config, conn = open_context(args)
    db_path = Path(args.db) if args.db else config.db_path()
    start = now_iso()
    try:
        erg = erstelle_backup(config, db_path, ziel=Path(args.ziel) if args.ziel else None)
    except Exception as exc:
        conn.execute("INSERT INTO run_log (schritt, start, ende, fehler) VALUES ('backup', ?, ?, ?)",
                     (start, now_iso(), f"{type(exc).__name__}: {exc}"))
        conn.commit()
        raise
    conn.execute(
        "INSERT INTO run_log (schritt, start, ende, zahlen_json, fehler) VALUES ('backup', ?, ?, ?, ?)",
        (start, now_iso(), json.dumps(erg.as_dict(), ensure_ascii=False), "\n".join(erg.warnungen) or None),
    )
    conn.commit()
    conn.close()
    print_json(erg.as_dict())
    return 2 if erg.warnungen else 0


if __name__ == "__main__":
    run(main, BackupFehler, OSError)
