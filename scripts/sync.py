"""CLI: Angebote von Fredy holen und in data/immo.db führen.

    python scripts/sync.py [--profile mfh-beispiel] [--config-dir config] [--db data/immo.db]

Exit-Code 0 = ok, 1 = Konfigurations-/Fredy-Fehler, 2 = Lauf mit Teilfehlern.
"""

from __future__ import annotations

from immo.cli import open_context, parser, print_json, run
from immo.fredy_client import FredyError, create_client
from immo.sync import run_sync


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--profile", help="nur dieses Profil (sonst alle aktiven)")
    args = ap.parse_args()

    config, conn = open_context(args)
    client = create_client(config)
    try:
        results = run_sync(conn, client, config, args.profile)
    finally:
        client.close()
        conn.close()

    print_json({s.profile_id: s.as_dict() for s in results})
    return 2 if any(s.fehler for s in results) else 0


if __name__ == "__main__":
    run(main, FredyError)
