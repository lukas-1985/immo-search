"""CLI: Claude-Extraktion prüfen und speichern.

    python scripts/save.py data/extraction/<datei>.json

Die Datei enthält {"ergebnisse": [ … ]} im Format des Extraktionsschemas.
Exit-Code 0 = alles angenommen, 2 = mindestens ein Ergebnis abgelehnt (Details in der Ausgabe).
"""

from __future__ import annotations

import json
from pathlib import Path

from immo.claude_io import save
from immo.cli import open_context, parser, print_json, run
from immo.db import now_iso


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("datei", type=Path, help="JSON-Datei mit den Ergebnissen")
    args = ap.parse_args()

    try:
        payload = json.loads(args.datei.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{args.datei}: nicht lesbar ({exc})") from exc

    config, conn = open_context(args)
    start = now_iso()
    report = save(conn, config, payload)
    zahlen = {"angenommen": len(report.angenommen), "abgelehnt": len(report.abgelehnt)}
    conn.execute(
        "INSERT INTO run_log (schritt, start, ende, zahlen_json) VALUES ('save', ?, ?, ?)",
        (start, now_iso(), json.dumps(zahlen)),
    )
    conn.commit()
    conn.close()
    print_json(report.as_dict())
    return 2 if report.abgelehnt else 0


if __name__ == "__main__":
    run(main, ValueError)
