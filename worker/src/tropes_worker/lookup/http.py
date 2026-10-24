"""One polite HTTP client for every metadata source.

Per-host rate limits (a minimum gap between requests to the same host, shared
across threads), one User-Agent that names the project, and a raw-response
cache on disk so a merge rule can change and be re-run over the whole library
without fetching anything again. Failures degrade to None plus a warning;
a flaky site should cost coverage, never the job.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

log = logging.getLogger("tropes_worker.lookup.http")
Headers = dict[str, str] | None
Params = dict[str, Any] | None

# Seconds between requests to one host. Wikidata and MusicBrainz state their expectations; the
# review sites get the slowest rate because we are reading pages, not an API.
HOST_GAP: dict[str, float] = {
    "www.wikidata.org": 0.35,
    "en.wikipedia.org": 0.2,
    "api.themoviedb.org": 0.25,
    "image.tmdb.org": 0.1,
    "api.myanimelist.net": 0.5,
    "store.steampowered.com": 1.0,
    "openlibrary.org": 0.5,
    "covers.openlibrary.org": 0.3,
    "musicbrainz.org": 1.1,
    "coverartarchive.org": 0.5,
    "itunes.apple.com": 0.5,
    "www.rottentomatoes.com": 2.0,
    "www.metacritic.com": 2.0,
    "www.goodreads.com": 2.0,
    "datasets.imdbws.com": 1.0,
}
DEFAULT_GAP = 1.0


@dataclass
class Cached:
    status: int
    body: str
    content_type: str
    fetched_at: float


@dataclass
class Fetcher:
    """Sync client. Safe to share across threads; the per-host gap is enforced with a lock per host."""

    cache_dir: Path
    user_agent: str = "TropeLog/0.1 (+https://github.com/wasabipesto-bot/tropes)"
    timeout: float = 30.0
    # Pass an httpx.MockTransport in tests.
    transport: httpx.BaseTransport | None = None
    # Entries older than this are refetched; None means the cache never expires (details rarely change).
    max_age_days: float | None = 30
    warnings: list[str] = field(default_factory=list)
    requests_made: int = 0
    cache_hits: int = 0

    def __post_init__(self) -> None:
        self._http = httpx.Client(
            headers={"User-Agent": self.user_agent}, timeout=self.timeout, transport=self.transport, follow_redirects=True
        )
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()

    def close(self) -> None:
        self._http.close()

    # Fetching -----------------------------------------------------------------------------------

    def get_json(self, url: str, params: dict[str, Any] | None = None, headers: Headers = None, *, cache: bool = True) -> Any:
        """Parsed JSON, or None on 404 or any failure (recorded in `warnings`)."""
        c = self._get(url, params, headers, cache=cache)
        if c is None or c.status >= 400:
            return None
        try:
            return json.loads(c.body)
        except ValueError:
            self.warn(f"{_host(url)}: response was not JSON")
            return None

    def get_text(self, url: str, params: Params = None, headers: Headers = None, *, cache: bool = True) -> str | None:
        c = self._get(url, params, headers, cache=cache)
        return None if c is None or c.status >= 400 else c.body

    def get_bytes(self, url: str, headers: dict[str, str] | None = None, *, max_bytes: int = 25_000_000) -> bytes | None:
        """Uncached binary fetch, for posters and the IMDb dataset."""
        self._wait(_host(url))
        try:
            r = self._http.get(url, headers=headers)
            self.requests_made += 1
            if r.status_code >= 400:
                if r.status_code != 404:
                    self.warn(f"{_host(url)}: HTTP {r.status_code} for {url}")
                return None
            if len(r.content) > max_bytes:
                self.warn(f"{_host(url)}: response over {max_bytes} bytes, skipped")
                return None
            return r.content
        except httpx.HTTPError as e:
            self.warn(f"{_host(url)}: {type(e).__name__}")
            return None

    def status(self, url: str) -> int | None:
        """HEAD-ish existence check (a GET with the body discarded, since some CDNs refuse HEAD)."""
        c = self._get(url, None, None, cache=True)
        return None if c is None else c.status

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
        log.warning(message)

    # Internals ----------------------------------------------------------------------------------

    def _get(self, url: str, params: dict[str, Any] | None, headers: Headers, *, cache: bool) -> Cached | None:
        full = url if not params else f"{url}?{urlencode(params, doseq=True)}"
        path = self._cache_path(full, headers)
        if cache:
            hit = self._read_cache(path)
            if hit is not None:
                self.cache_hits += 1
                return hit
        host = _host(url)
        self._wait(host)
        try:
            r = self._http.get(url, params=params, headers=headers)
            self.requests_made += 1
        except httpx.HTTPError as e:
            self.warn(f"{host}: {type(e).__name__}")
            return None
        if r.status_code == 429 or r.status_code >= 500:
            # One retry after a pause; then give up on this URL.
            time.sleep(3.0)
            try:
                r = self._http.get(url, params=params, headers=headers)
                self.requests_made += 1
            except httpx.HTTPError as e:
                self.warn(f"{host}: {type(e).__name__}")
                return None
        if r.status_code >= 400 and r.status_code != 404:
            self.warn(f"{host}: HTTP {r.status_code}")
        c = Cached(status=r.status_code, body=r.text, content_type=r.headers.get("content-type", ""), fetched_at=time.time())
        if cache and (r.status_code < 500 and r.status_code != 429):
            self._write_cache(path, c)
        return c

    def _wait(self, host: str) -> None:
        gap = HOST_GAP.get(host, DEFAULT_GAP)
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        with lock:
            now = time.monotonic()
            due = self._last.get(host, 0.0) + gap
            if due > now:
                time.sleep(due - now)
            self._last[host] = time.monotonic()

    def _cache_path(self, full_url: str, headers: dict[str, str] | None) -> Path:
        # Headers that select the representation (an API key does not) are part of the key.
        picked = {k.lower(): v for k, v in (headers or {}).items() if k.lower() in ("accept", "accept-language")}
        extra = "".join(f"{k}={v}" for k, v in sorted(picked.items()))
        digest = hashlib.sha1((full_url + extra).encode()).hexdigest()
        return self.cache_dir / _host(full_url) / f"{digest}.json"

    def _read_cache(self, path: Path) -> Cached | None:
        if not path.is_file():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        if self.max_age_days is not None and time.time() - d.get("fetched_at", 0) > self.max_age_days * 86400:
            return None
        return Cached(d["status"], d["body"], d.get("content_type", ""), d.get("fetched_at", 0))

    def _write_cache(self, path: Path, c: Cached) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {"status": c.status, "body": c.body, "content_type": c.content_type, "fetched_at": c.fetched_at}
            path.write_text(json.dumps(data), encoding="utf-8")
        except OSError as e:
            log.warning("cache write failed: %s", e)


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""
