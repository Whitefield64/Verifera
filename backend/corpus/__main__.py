"""Corpus CLI: python -m corpus {sync,status}."""

import argparse
import sys

from corpus import sync as sync_module


def main() -> int:
    parser = argparse.ArgumentParser(prog="corpus", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    sync_cmd = commands.add_parser(
        "sync", help="Fetch the pack's sources into the ingestion inbox"
    )
    sync_cmd.add_argument(
        "--check",
        action="store_true",
        help="Report what changed upstream without downloading anything",
    )
    sync_cmd.add_argument("--source", default=None, help="Only this source id")

    commands.add_parser("status", help="Declared sources vs what the manifest holds")

    args = parser.parse_args()
    if args.command == "sync":
        return sync_module.sync(check_only=args.check, only_id=args.source)
    if args.command == "status":
        return sync_module.status()
    return 2


if __name__ == "__main__":
    sys.exit(main())
