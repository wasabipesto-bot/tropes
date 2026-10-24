"""Command line entry point: `tropes-worker <command>`."""

from __future__ import annotations

import argparse
import logging

from .client import SiteClient
from .settings import Settings


def build_parser() -> argparse.ArgumentParser:
    # Shared options are attached to both levels so they work before or
    # after the subcommand: `tropes-worker ping --site X` and `--site X ping`.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--site", default=None, help="site base URL (env TROPES_SITE_URL)")
    common.add_argument("--token", default=None, help="worker bearer token (env TROPES_API_TOKEN)")
    common.add_argument("-v", "--verbose", action="store_true")
    p = argparse.ArgumentParser(prog="tropes-worker", parents=[common])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("ping", parents=[common], help="check that the site is up and the database answers")
    run = sub.add_parser("run", parents=[common], help="claim and run jobs")
    run.add_argument("--once", action="store_true", help="run at most one job, then exit")
    run.add_argument("--kinds", default=None, help="comma-separated job kinds to handle (default: all)")
    sub.add_parser("sync", parents=[common], help="read the Notion Media Log once and hand the rows to the site")
    lk = sub.add_parser("lookup", parents=[common], help="resolve identities for a sample of the library; writes nothing")
    lk.add_argument("--sample", type=int, default=50, help="how many entries, spread across types (default 50)")
    lk.add_argument("--ids", default=None, help="comma-separated media ids instead of a sample")
    lk.add_argument("--out", default=None, help="write the markdown report here")
    ev = sub.add_parser("eval", parents=[common], help="score the scan against verified instances; writes nothing")
    ev.add_argument("--trope", action="append", default=[], help="trope slug (repeatable); default: all with verified instances")
    ev.add_argument("--out", default=None, help="write the report as JSON here")
    return p


def cmd_ping(client: SiteClient) -> int:
    h = client.health()
    state = "ok" if h.ok else "NOT OK"
    print(f"{state}: site {h.version or '?'}, {h.media} media items")
    return 0 if h.ok else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings.from_env()
    site = args.site or settings.site_url
    token = args.token or settings.api_token
    with SiteClient(site, token) as client:
        if args.command == "ping":
            return cmd_ping(client)
        if args.command == "run":
            from .runner import run_forever, run_one

            kinds = args.kinds.split(",") if args.kinds else None
            if args.once:
                return 0 if run_one(settings, client, kinds) else 3
            run_forever(settings, client, kinds)
            return 0
        if args.command == "sync":
            from .jobs.sync_notion import sync_once

            report = sync_once(settings, client)
            print(
                f"{report['rows']} rows: inserted {report['inserted']}, updated {report['updated']}, "
                f"unchanged {report['unchanged']}, skipped {len(report.get('skipped', []))}, missing {report.get('missing', 0)}"
            )
            return 0
        if args.command == "lookup":
            from .lookup.report import run_sample

            ids = [int(x) for x in args.ids.split(",")] if args.ids else None
            report = run_sample(settings, client, sample=args.sample, ids=ids)
            if args.out:
                with open(args.out, "w", encoding="utf-8") as fh:
                    fh.write(report + "\n")
            print(report)
            return 0
        if args.command == "eval":
            from .eval import evaluate

            return evaluate(settings, client, args.trope or None, args.out)
    return 2
