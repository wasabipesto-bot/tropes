"""HTTP client for the site's job API.

The worker is a client of the site and nothing else: it never touches the
SQLite file. Every call goes through this class so the contract stays in one
place. Shapes mirror web/src/lib/jobs/schemas.ts.
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


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int


class JobCancelled(Exception):
    """The owner discarded the job while it was running."""


class SiteClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
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

    def _post(self, path: str, body: Any = None) -> httpx.Response:
        r = self._http.post(path, json=body if body is not None else {})
        r.raise_for_status()
        return r

    def health(self) -> Health:
        data = self._get("/api/health")
        return Health(ok=bool(data.get("ok")), media=int(data.get("media", 0)), version=str(data.get("version", "")))

    # Jobs ---------------------------------------------------------------

    def claim(self, kinds: list[str]) -> Job | None:
        r = self._post("/api/jobs/claim", {"kinds": kinds})
        if r.status_code == 204:
            return None
        d = r.json()
        return Job(id=int(d["id"]), kind=str(d["kind"]), payload=dict(d.get("payload") or {}), attempts=int(d.get("attempts", 1)))

    def progress(self, job_id: int, done: int, total: int, note: str | None = None) -> None:
        body: dict[str, Any] = {"done": done, "total": total}
        if note:
            body["note"] = note
        status = self._post(f"/api/jobs/{job_id}/progress", body).json().get("status")
        if status == "cancelled":
            raise JobCancelled(job_id)

    def result(self, job_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/api/jobs/{job_id}/result", body).json()

    def fail(self, job_id: int, error: str) -> None:
        self._post(f"/api/jobs/{job_id}/fail", {"error": error[:4000]})

    def job(self, job_id: int) -> dict[str, Any]:
        return self._get(f"/api/jobs/{job_id}")

    def create_job(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Queue a job from the worker side (the sync timer uses this). The site validates the payload."""
        return self._post("/api/jobs", {"kind": kind, "payload": payload}).json()

    def import_notion(self, rows: list[dict[str, Any]], *, complete: bool) -> dict[str, Any]:
        """Hand the Media Log rows to the site's importer; `complete` means every row was read, so missing ones can be marked."""
        return self._post("/api/import/notion", {"rows": rows, "complete": complete}).json()

    # Exports ------------------------------------------------------------

    def tropes(self) -> list[dict[str, Any]]:
        return list(self._get("/api/export/tropes")["tropes"])

    def subjects(self) -> dict[str, list[dict[str, Any]]]:
        return self._get("/api/export/subjects")

    def genres(self) -> dict[str, Any]:
        return self._get("/api/export/genres")

    def upload_poster(self, media_id: int, source: str, files: dict[int, bytes], *, pending: bool = True) -> dict[str, Any]:
        """Three WebP sizes in one multipart request; pending files wait for the lookup to be committed."""
        data = {"source": source, "pending": "1" if pending else "0"}
        parts = {f"p{w}": (f"{media_id}-{w}.webp", body, "image/webp") for w, body in files.items()}
        r = self._http.post(f"/api/media/{media_id}/poster", data=data, files=parts)
        r.raise_for_status()
        return r.json()

    def post_sources(self, works: list[dict[str, Any]]) -> dict[str, Any]:
        """What the media worker found on the disk for some works (one call per batch of works)."""
        return self._post("/api/sources", {"works": works}).json()

    def post_source_text(self, source_id: int, text: str, how: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """The text extracted for one local source; an empty text with a reason marks it as tried."""
        return self._post(f"/api/sources/{source_id}/text", {"text": text, "source": how, "meta": meta or {}}).json()

    def source_text(self, source_id: int) -> str | None:
        """The extracted text of a local source, or None when there is none."""
        r = self._http.get(f"/api/export/text/{source_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.text

    def frames_for(self, job_id: int) -> list[dict[str, Any]]:
        """A scan's proposals for visual tropes with their pending frames (plan D12)."""
        return list(self._get(f"/api/export/frames/{job_id}")["items"])

    def pending_frame(self, proposal_id: int, name: str) -> bytes | None:
        r = self._http.get(f"/evidence/pending/{proposal_id}/{name}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    def link_text(self, media_id: int, path: str, label: str = "") -> dict[str, Any]:
        """Register a text the worker fetched itself (a Fandom transcript) as a source for a work."""
        return self._post("/api/sources/text", {"mediaId": media_id, "path": path, "label": label}).json()

    def upload_sheet(self, source_id: int, n: int, data: bytes) -> dict[str, Any]:
        """Contact sheet n (JPEG) for a video source; the site counts them in the source's meta."""
        r = self._http.put(f"/api/sources/{source_id}/sheet/{n}", content=data, headers={"content-type": "image/jpeg"})
        r.raise_for_status()
        return r.json()

    def sheet(self, source_id: int, n: int) -> bytes | None:
        r = self._http.get(f"/api/export/sheet/{source_id}/{n}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.content

    def upload_evidence(self, target: str, kind: str, at: float, data: bytes, ext: str) -> dict[str, Any]:
        """A frame or clip for `proposal:<id>` (beside the quote on the review page) or `evidence:<id>` (onto the instance)."""
        r = self._http.post(
            "/api/evidence/file",
            data={"target": target, "kind": kind, "at": f"{at:.3f}"},
            files={"file": (f"{kind}.{ext}", data, "image/webp" if ext == "webp" else "video/mp4")},
        )
        r.raise_for_status()
        return r.json()

    def dossier(self, kind: str, subject_id: int) -> dict[str, Any] | None:
        r = self._http.get(f"/api/dossiers/{kind}/{subject_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
