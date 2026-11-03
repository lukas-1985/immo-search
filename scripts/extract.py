"""CLI: Offene Angebote mit Codex/ChatGPT auswerten und geprüft speichern."""

from immo.cli import open_context, parser, print_json, run
from immo.codex_extraktion import extrahiere


def main() -> int:
    ap = parser(__doc__)
    ap.add_argument("--profile")
    ap.add_argument("--listing", type=int)
    ap.add_argument("--reextract", action="store_true")
    args = ap.parse_args()
    if args.reextract and args.listing is None:
        ap.error("--reextract braucht --listing")
    config, conn = open_context(args)
    try:
        ergebnis = extrahiere(conn, config, profil=args.profile, listing_id=args.listing, reextract=args.reextract)
        print_json(ergebnis)
        return 2 if ergebnis["abgelehnt"] or ergebnis["feld_abgelehnt"] or ergebnis["offen"] else 0
    except (OSError, ValueError) as exc:
        print_json({"fehler": str(exc)})
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    run(main, ValueError)
