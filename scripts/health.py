"""CLI: Health-Prüfung (Portale liefern, Sync und Backup aktuell, Server antwortet), Ergebnis in run_log.

    python scripts/health.py [--ohne-server] [--streng]

Probleme werden als WARNUNG ausgegeben und in run_log (Schritt `health`, Spalte `fehler`) vermerkt.
Exit-Code 0, auch bei Problemen – mit `--streng` dann 2. Exit-Code 1 nur, wenn die Prüfung selbst scheitert.
"""

from __future__ import annotations

from immo.cli import open_context, parser, print_json, run
from immo.db import now_iso
from immo.health import frage_server, protokolliere, pruefe


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--ohne-server", action="store_true", help="/health des Servers nicht abfragen")
    ap.add_argument("--streng", action="store_true", help="Exit-Code 2, wenn eine Prüfung fehlschlägt")
    args = ap.parse_args()

    config, conn = open_context(args)
    start = now_iso()
    erg = pruefe(conn, config, server_abfrage=None if args.ohne_server else frage_server)
    protokolliere(conn, erg, start)
    conn.close()
    print_json(erg.as_dict())
    for p in erg.probleme:
        print(f"WARNUNG: {p}")  # stdout: landet so sicher im Log von run.ps1
    return 2 if args.streng and not erg.ok else 0


if __name__ == "__main__":
    run(main)
