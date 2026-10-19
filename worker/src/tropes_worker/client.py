"""HTTP client for the site's job API.

The worker is a client of the site and nothing else: it never touches the
SQLite file. Every call goes through this class so the contract stays in one
place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Health:
    ok: bool
    media: int
    version: str


class SiteClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers = {"User-Agent": "tropes-worker"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> SiteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, path: str, **params: Any) -> Any:
        r = self._http.get(path, params=params or None)
        r.raise_for_status()
        return r.json()

    def health(self) -> Health:
        data = self._get("/api/health")
        return Health(
            ok=bool(data.get("ok")),
            media=int(data.get("media", 0)),
            version=str(data.get("version", "")),
        )
