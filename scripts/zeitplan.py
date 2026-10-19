"""CLI: Zeitplan aus settings.yaml als JSON ausgeben (für scripts/install_tasks.ps1).

    python scripts/zeitplan.py
"""

from __future__ import annotations

from immo.cli import parser, print_json, run
from immo.config import load_config


def main() -> int:
    args = parser(__doc__.splitlines()[0]).parse_args()
    s = load_config(args.config_dir).settings
    print_json({"run": s.schedule.run.model_dump(by_alias=True), "backup": s.schedule.backup.model_dump(),
                "server_port": s.server.port})
    return 0


if __name__ == "__main__":
    run(main)
