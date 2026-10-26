"""OpenSubtitles REST API as the third subtitle source: search by IMDb id (and episode), download the best English file.

Needs an API key (`TROPES_OPENSUBTITLES_KEY`); with a user login (`TROPES_OPENSUBTITLES_USER`/`_PASSWORD`)
the daily quota is the account's (20 free), otherwise the anonymous 5. One request a second; the
remaining quota is read from each download and the job stops asking once it is spent.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("tropes_worker.media.opensubtitles")
API = "https://api.opensubtitles.com/api/v1"


@dataclass
class OpenSubtitles:
    api_key: str
    user: str | None = None
    password: str | None = None
    user_agent: str = "TropeLog v0.1"
    transport: httpx.BaseTransport | None = None
    remaining: int | None = None
    _token: str | None = field(default=None, repr=False)
    _last: float = 0.0

    def __post_init__(self) -> None:
        self._http = httpx.Client(
            base_url=API,
            headers={"Api-Key": self.api_key, "User-Agent": self.user_agent, "Accept": "application/json"},
            timeout=60,
            transport=self.transport,
            follow_redirects=True,
        )

    def _wait(self) -> None:
        gap = 1.0 - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def login(self) -> bool:
        if not (self.user and self.password):
            return False
        self._wait()
        r = self._http.post("/login", json={"username": self.user, "password": self.password})
        if r.status_code != 200:
            log.warning("opensubtitles login failed: %s", r.status_code)
            return False
        self._token = r.json().get("token")
        return bool(self._token)

    def search(
        self, imdb_id: str, season: int | None = None, episode: int | None = None, language: str = "en"
    ) -> list[dict[str, Any]]:
        """Subtitle files for a title (tt…) or an episode, best first: plain over hearing-impaired, trusted, most downloaded."""
        params: dict[str, Any] = {
            "imdb_id": imdb_id[2:] if imdb_id.startswith("tt") else imdb_id,
            "languages": language,
            "order_by": "download_count",
            "order_direction": "desc",
        }
        if season is not None and episode is not None:
            params.update({"season_number": season, "episode_number": episode})
        # The API answers 301 to any query that is not alphabetical and lowercase.
        params = {k: (v.lower() if isinstance(v, str) else v) for k, v in sorted(params.items())}
        self._wait()
        r = self._http.get("/subtitles", params=params, headers=self._headers())
        if r.status_code != 200:
            log.warning("opensubtitles search %s: %s", params, r.status_code)
            return []
        items = r.json().get("data", [])
        files = []
        for it in items:
            a = it.get("attributes", {})
            for f in a.get("files", []):
                files.append(
                    {
                        "file_id": f.get("file_id"),
                        "name": f.get("file_name"),
                        "hi": a.get("hearing_impaired"),
                        "trusted": a.get("from_trusted"),
                        "downloads": a.get("download_count", 0),
                        "release": a.get("release"),
                    }
                )
        files.sort(key=lambda f: (bool(f["hi"]), not f["trusted"], -f["downloads"]))
        return files

    def download(self, file_id: int) -> str | None:
        """The subtitle text, or None when the quota is spent or the request fails."""
        if self.remaining is not None and self.remaining <= 0:
            return None
        self._wait()
        r = self._http.post("/download", json={"file_id": file_id, "sub_format": "srt"}, headers=self._headers())
        if r.status_code != 200:
            log.warning("opensubtitles download %s: %s %s", file_id, r.status_code, r.text[:120])
            if r.status_code in (406, 429):
                self.remaining = 0
            return None
        d = r.json()
        self.remaining = d.get("remaining")
        link = d.get("link")
        if not link:
            return None
        self._wait()
        s = self._http.get(link)
        return s.text if s.status_code == 200 else None

    def fetch(self, imdb_id: str, season: int | None = None, episode: int | None = None) -> str | None:
        """Search and download the best file in one go."""
        files = self.search(imdb_id, season, episode)
        for f in files[:2]:
            text = self.download(f["file_id"])
            if text:
                return text
        return None
