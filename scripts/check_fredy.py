"""CLI: Diagnose gegen das laufende Fredy (Phase 1) – liest nur, schreibt nichts in Fredy oder die DB.

    python scripts/check_fredy.py [--stichprobe 3]

Bericht auf stdout; Bericht + Rohdaten-Stichprobe zusätzlich unter data/fredy_check/<zeit>.json.
"""

from __future__ import annotations

import json
from datetime import datetime

from immo.cli import parser, print_json, run
from immo.config import PROJECT_ROOT, load_config
from immo.fredy_check import check
from immo.fredy_client import FredyError, create_client


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--stichprobe", type=int, default=3, help="Rohdatensätze je Job in der Datei (Standard 3)")
    args = ap.parse_args()

    config = load_config(args.config_dir)
    client = create_client(config)
    try:
        bericht, roh = check(client, config, args.stichprobe)
    finally:
        client.close()

    out_dir = PROJECT_ROOT / "data" / "fredy_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    datei = out_dir / f"{datetime.now():%Y%m%d-%H%M}.json"
    datei.write_text(json.dumps({"bericht": bericht, "rohdaten": roh}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print_json(bericht)
    print(f"\nGespeichert: {datei}")
    return 0


if __name__ == "__main__":
    run(main, FredyError)
