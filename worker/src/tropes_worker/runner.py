"""The claim loop: take a job, run it, post the result, repeat."""

from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Callable
from typing import Any

from .client import JobCancelled, SiteClient
from .settings import Settings

log = logging.getLogger("tropes_worker")

JobFn = Callable[["Context", dict[str, Any]], dict[str, Any]]


class Context:
    """What every job gets: the settings, the site client, and the job id for progress."""

    def __init__(self, settings: Settings, client: SiteClient, job_id: int) -> None:
        self.settings = settings
        self.client = client
        self.job_id = job_id

    def progress(self, done: int, total: int, note: str | None = None) -> None:
        self.client.progress(self.job_id, done, total, note)


def registry() -> dict[str, JobFn]:
    from .jobs import build_dossiers, check_subject, lookup_media, ping, scan_trope, sync_notion, write_blurbs

    return {
        "ping": ping.run,
        "build_dossiers": build_dossiers.run,
        "scan_trope": scan_trope.run,
        "check_subject": check_subject.run,
        "sync_notion": sync_notion.run,
        "lookup_media": lookup_media.run,
        "write_blurbs": write_blurbs.run,
    }


def post_result(client: SiteClient, job_id: int, result: dict[str, Any], attempts: int = 4) -> None:
    """A long job's result is worth a few retries: the site may be restarting at that moment."""
    for i in range(attempts):
        try:
            client.result(job_id, result)
            return
        except Exception as e:  # noqa: BLE001 - retried below
            if i == attempts - 1:
                raise
            log.warning("posting result for job %d failed (%s); retrying", job_id, type(e).__name__)
            time.sleep(3 * (i + 1))


def run_one(settings: Settings, client: SiteClient, kinds: list[str] | None = None) -> bool:
    """Claim and run a single job. Returns False when the queue was empty."""
    handlers = registry()
    job = client.claim(kinds or list(handlers))
    if job is None:
        return False
    log.info("job %d %s claimed (attempt %d)", job.id, job.kind, job.attempts)
    ctx = Context(settings, client, job.id)
    started = time.monotonic()
    try:
        result = handlers[job.kind](ctx, job.payload)
        post_result(client, job.id, result)
        log.info("job %d done in %.0fs", job.id, time.monotonic() - started)
    except JobCancelled:
        log.info("job %d cancelled by the owner", job.id)
    except Exception as e:  # noqa: BLE001 - the job must be marked failed whatever happened
        log.error("job %d failed: %s", job.id, e)
        client.fail(job.id, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}")
    return True


def sync_due(settings: Settings, last: float | None, now: float) -> bool:
    """The Notion sync timer: every `notion_sync_minutes` when a key is configured. The first run is immediate."""
    if not settings.notion_api_key or settings.notion_sync_minutes <= 0:
        return False
    return last is None or now - last >= settings.notion_sync_minutes * 60


def run_forever(settings: Settings, client: SiteClient, kinds: list[str] | None = None) -> None:
    log.info("worker started against %s (model %s)", settings.site_url, settings.model)
    last_sync: float | None = None
    while True:
        try:
            if (kinds is None or "sync_notion" in kinds) and sync_due(settings, last_sync, time.monotonic()):
                last_sync = time.monotonic()
                client.create_job("sync_notion", {})
            if not run_one(settings, client, kinds):
                time.sleep(settings.poll_seconds)
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 - keep polling through site restarts
            log.warning("claim failed: %s; retrying", e)
            time.sleep(max(settings.poll_seconds, 5))
