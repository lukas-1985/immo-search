"""CLI: Ein zeitgesteuerter Lauf (run.ps1) als Job – für die Aufgabenplanung.

    python scripts/lauf.py [--profile mfh-kl]

Der Lauf erscheint in der Oberfläche unter „Läufe“ (ausgelöst von `zeitplan`), sein Log liegt unter
data/logs/job-<id>.log. Ausgeführt wird er hier im Prozess, nicht im Server – er läuft also auch,
wenn der Server gerade nicht läuft. Exit-Code 0 ok, 2 Lauf mit Fehlern oder Teilfehlern.
"""

from __future__ import annotations

from pathlib import Path

from immo.cli import parser, print_json, run
from immo.config import load_config
from immo.jobs import JobFehler, direkt_ausfuehren


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--profile", help="nur dieses Profil (sonst alle aktiven)")
    args = ap.parse_args()

    config = load_config(args.config_dir)
    db_path = Path(args.db) if args.db else config.db_path()
    job_id, ok = direkt_ausfuehren(config, db_path, "lauf", {"profil": args.profile}, "zeitplan")
    print_json({"job_id": job_id, "ok": ok, "hinweis": None if job_id else "derselbe Lauf ist schon aktiv – übersprungen"})
    return 0 if ok else 2


if __name__ == "__main__":
    run(main, JobFehler)
