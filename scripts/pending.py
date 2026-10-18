"""CLI: Noch nicht ausgewertete Angebote kompakt für Claude ausgeben (JSON auf stdout).

    python scripts/pending.py [--profile mfh-beispiel] [--limit 20]
    python scripts/pending.py --listing 42 --reextract
"""

from __future__ import annotations

from immo.claude_io import pending
from immo.cli import open_context, parser, print_json, run


def main() -> int:
    ap = parser(__doc__.splitlines()[0])
    ap.add_argument("--profile", help="nur dieses Profil (sonst alle aktiven)")
    ap.add_argument("--limit", type=int, default=20, help="höchstens so viele Angebote (Standard 20)")
    ap.add_argument("--listing", type=int, help="nur dieses Angebot")
    ap.add_argument("--reextract", action="store_true", help="mit --listing: auch wenn schon ausgewertet")
    args = ap.parse_args()
    if args.reextract and args.listing is None:
        ap.error("--reextract nur zusammen mit --listing")

    config, conn = open_context(args)
    print_json(pending(conn, config, args.limit, args.profile, args.listing, args.reextract))
    conn.close()
    return 0


if __name__ == "__main__":
    run(main)
