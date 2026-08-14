"""Ingestion CLI: python -m ingestion {ingest,status,check-stability,rebuild-workspace}."""

import argparse
import sys
from pathlib import Path

from ingestion import pipeline


def main() -> int:
    parser = argparse.ArgumentParser(prog="ingestion", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Process every file in data/raw/")
    ingest.add_argument("--raw-dir", type=Path, default=None)

    commands.add_parser("status", help="Document status and bbox coverage")

    stability = commands.add_parser(
        "check-stability", help="Re-parse a published document and compare its chunk_ids"
    )
    stability.add_argument("doc_id")

    rebuild_cmd = commands.add_parser(
        "rebuild-workspace",
        help="Rematerialize sections/ + summaries from the chunks in Postgres "
        "(no re-parse, no re-embed)",
    )
    rebuild_cmd.add_argument("--doc", default=None, help="Only this doc_id")
    rebuild_cmd.add_argument("--skip-summaries", action="store_true")
    rebuild_cmd.add_argument(
        "--force-summaries", action="store_true", help="Regenerate existing summaries too"
    )

    args = parser.parse_args()
    if args.command == "ingest":
        outcomes = pipeline.ingest_folder(args.raw_dir)
        return 1 if any(o.outcome == "fail" for o in outcomes) else 0
    if args.command == "status":
        pipeline.print_status()
        return 0
    if args.command == "check-stability":
        return 0 if pipeline.check_stability(args.doc_id) else 1
    if args.command == "rebuild-workspace":
        from ingestion import rebuild

        return rebuild.rebuild(
            only_doc=args.doc,
            skip_summaries=args.skip_summaries,
            force_summaries=args.force_summaries,
        )
    return 2


if __name__ == "__main__":
    sys.exit(main())
