"""CLI: Alle Angebote neu bewerten (Ausschlusskriterien, KPIs, Score, Kaufpreisempfehlung).

    python scripts/score.py [--profile mfh-beispiel] [--top 5]
"""

from __future__ import annotations

import json

from immo.cli import open_context, parser, print_json, run
from immo.db import now_iso
from immo.scoring import ranking, run_score


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--profile", help="nur dieses Profil (sonst alle aktiven)")
    ap.add_argument("--top", type=int, default=5, help="so viele Spitzenreiter je Profil ausgeben")
    args = ap.parse_args()

    config, conn = open_context(args)
    start = now_iso()
    out = {}
    for stats in run_score(conn, config, args.profile):
        conn.execute(
            "INSERT INTO run_log (schritt, profile_id, start, ende, zahlen_json) VALUES ('score', ?, ?, ?, ?)",
            (stats.profile_id, start, now_iso(), json.dumps(stats.__dict__, ensure_ascii=False)),
        )
        top = [
            {"listing_id": r["id"], "titel": r["titel"], "score": r["score"], "preis": r["preis"],
             "kaufpreisempfehlung": None if r["kaufpreisempfehlung"] is None else round(r["kaufpreisempfehlung"]),
             "preisabstand": None if r["preisabstand"] is None else round(r["preisabstand"], 3)}
            for r in ranking(conn, config, stats.profile_id, args.top)
        ]
        out[stats.profile_id] = {**{k: v for k, v in stats.__dict__.items() if k != "profile_id"}, "top": top}
    conn.commit()
    conn.close()
    print_json(out)
    return 0


if __name__ == "__main__":
    run(main)
