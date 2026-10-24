"""sync_notion: read the Media Log through Notion's API and post every row to the site's importer."""

from __future__ import annotations

from typing import Any

from ..client import SiteClient
from ..notion import fetch_rows
from ..runner import Context
from ..settings import Settings


def sync_once(settings: Settings, client: SiteClient) -> dict[str, Any]:
    rows = fetch_rows(settings)
    report = client.import_notion(rows, complete=True)
    report["rows"] = len(rows)
    return report


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    ctx.progress(0, 2, "reading Notion")
    report = sync_once(ctx.settings, ctx.client)
    ctx.progress(2, 2, "done")
    warnings = [f"skipped: {s['reason']}" for s in report.get("skipped", [])][:20]
    summary = {k: report.get(k) for k in ("rows", "inserted", "updated", "unchanged", "missing", "queued")}
    return {"summary": summary, "warnings": warnings}
