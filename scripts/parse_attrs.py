"""CLI: Regelbasierte Extraktion für alle aktiven Angebote (Quelle `regel`).

    python scripts/parse_attrs.py [--profile mfh-beispiel]
"""

from __future__ import annotations

import json

from immo.claude_io import objektart_by_listing
from immo.cli import open_context, parser, print_json, run
from immo.db import now_iso
from immo.parse_attrs import run_parse_attrs


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--profile", help="nur dieses Profil (sonst alle aktiven)")
    args = ap.parse_args()

    config, conn = open_context(args)
    start = now_iso()
    stats = run_parse_attrs(conn, objektart_by_listing(conn, config, args.profile))
    conn.execute(
        "INSERT INTO run_log (schritt, profile_id, start, ende, zahlen_json) VALUES ('parse_attrs', ?, ?, ?, ?)",
        (args.profile, start, now_iso(), json.dumps(stats.__dict__, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    print_json(stats.__dict__)
    return 0


if __name__ == "__main__":
    run(main)
