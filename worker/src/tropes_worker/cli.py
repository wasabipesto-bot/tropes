"""Command line entry point: `tropes-worker <command>`."""

from __future__ import annotations

import argparse
import os
import sys

from .client import SiteClient


def build_parser() -> argparse.ArgumentParser:
    # Shared options are attached to both levels so they work before or
    # after the subcommand: `tropes-worker ping --site X` and `--site X ping`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--site",
        default=os.environ.get("TROPES_SITE_URL", "http://127.0.0.1:4321"),
        help="site base URL (env TROPES_SITE_URL)",
    )
    common.add_argument(
        "--token",
        default=os.environ.get("TROPES_API_TOKEN"),
        help="worker bearer token (env TROPES_API_TOKEN)",
    )
    p = argparse.ArgumentParser(prog="tropes-worker", parents=[common])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "ping", parents=[common], help="check that the site is up and the database answers"
    )
    return p


def cmd_ping(client: SiteClient) -> int:
    h = client.health()
    state = "ok" if h.ok else "NOT OK"
    print(f"{state}: site {h.version or '?'}, {h.media} media items")
    return 0 if h.ok else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with SiteClient(args.site, args.token) as client:
        if args.command == "ping":
            return cmd_ping(client)
    return 2


if __name__ == "__main__":
    sys.exit(main())
