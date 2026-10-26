"""Configuration, read once from the environment (and a .env in the cwd or the repo root)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    here = Path.cwd()
    for candidate in (here / ".env", here.parent / ".env", Path(__file__).resolve().parents[3] / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


@dataclass(frozen=True)
class Settings:
    site_url: str
    api_token: str | None
    openrouter_api_key: str | None
    model: str
    model_dossier: str
    concurrency: int
    temperature: float
    sources_dir: Path
    text_cache_dir: Path
    # D7: a text over this many tokens (about 4 characters each) is read in season blocks.
    text_cap_tokens: int
    # D6: Whisper on the media worker for files with no subtitle; medium.en is the owner's choice for celebrimbor.
    whisper_model: str
    whisper_threads: int
    # The media worker re-indexes the disk every this many hours (0 disables); the chain goes on to
    # dossiers and a trope recheck only when auto_dossier is on (the owner's call: it spends model money).
    index_hours: float
    auto_dossier: bool
    midden_key: str | None
    midden_url: str
    midden_blog: str
    # Pass thresholds (plan D15), all overridable.
    pass1_batch: int
    pass2_min_score: float
    pass2_cap: int
    unchecked_below: float
    # Send response_format json_schema (plus the healing plugin). Off by default: with DeepSeek it degenerates into
    # enormous, truncated outputs; prompt-only JSON validated client-side is fast and complete.
    json_schema: bool
    response_healing: bool
    # OpenRouter reasoning control: off, low, medium, high, or default (send nothing).
    reasoning: str
    poll_seconds: float
    call_timeout: float
    # Phase 4: external metadata.
    notion_api_key: str | None
    notion_data_source: str
    # Minutes between Notion syncs queued by the worker loop; 0 disables the timer.
    notion_sync_minutes: float
    tmdb_token: str | None
    mal_client_id: str | None
    lookup_cache_dir: Path
    user_agent: str
    # Phase 5: the media worker's view of the disk (empty on the model worker) and the subtitle fallback.
    media_root: str | None
    opensubtitles_key: str | None
    opensubtitles_user: str | None
    opensubtitles_password: str | None

    @classmethod
    def from_env(cls) -> Settings:
        _load_env()
        env = os.environ.get
        root = Path(__file__).resolve().parents[3]
        model = env("TROPES_MODEL", "deepseek/deepseek-v4.1-flash-1017")
        return cls(
            site_url=env("TROPES_SITE_URL", "http://127.0.0.1:4321").rstrip("/"),
            api_token=env("TROPES_API_TOKEN") or None,
            openrouter_api_key=env("OPENROUTER_API_KEY") or None,
            model=model,
            model_dossier=env("TROPES_MODEL_DOSSIER", model),
            concurrency=int(env("TROPES_LLM_CONCURRENCY", "8")),
            temperature=float(env("TROPES_TEMPERATURE", "0.3")),
            sources_dir=Path(env("TROPES_SOURCES_DIR", str(root / "data" / "sources"))),
            text_cache_dir=Path(env("TROPES_TEXT_CACHE_DIR", str(root / "data" / "text"))),
            text_cap_tokens=int(env("TROPES_TEXT_CAP_TOKENS", "600000")),
            whisper_model=env("TROPES_WHISPER_MODEL", "medium.en"),
            whisper_threads=int(env("TROPES_WHISPER_THREADS", "8")),
            index_hours=float(env("TROPES_INDEX_HOURS", "168")),
            auto_dossier=env("TROPES_AUTO_DOSSIER", "0").lower() in ("1", "true", "yes"),
            midden_key=env("TROPES_MIDDEN_KEY") or None,
            midden_url=env("TROPES_MIDDEN_URL", "https://beta.midden.net/api/search"),
            midden_blog=env("TROPES_MIDDEN_BLOG", "wasabipesto"),
            pass1_batch=int(env("TROPES_PASS1_BATCH", "25")),
            pass2_min_score=float(env("TROPES_PASS2_MIN_SCORE", "0.3")),
            pass2_cap=int(env("TROPES_PASS2_CAP", "60")),
            unchecked_below=float(env("TROPES_UNCHECKED_BELOW", "0.5")),
            json_schema=env("TROPES_JSON_SCHEMA", "0") in ("1", "true", "yes"),
            response_healing=env("TROPES_RESPONSE_HEALING", "1") not in ("0", "false", "no"),
            reasoning=env("TROPES_REASONING", "off").lower(),
            poll_seconds=float(env("TROPES_POLL_SECONDS", "2")),
            call_timeout=float(env("TROPES_CALL_TIMEOUT", "120")),
            notion_api_key=env("NOTION_API_KEY") or None,
            notion_data_source=env("NOTION_DATA_SOURCE", "993327c5-6f33-4429-ad1a-88a0d603bded"),
            notion_sync_minutes=float(env("TROPES_NOTION_SYNC_MINUTES", "15")),
            tmdb_token=env("TROPES_TMDB_TOKEN") or None,
            mal_client_id=env("TROPES_MAL_CLIENT_ID") or None,
            lookup_cache_dir=Path(env("TROPES_LOOKUP_CACHE_DIR", str(root / "data" / "cache" / "lookup"))),
            user_agent=env("TROPES_USER_AGENT", "TropeLog/0.1 (+https://github.com/wasabipesto-bot/tropes)"),
            media_root=env("TROPES_MEDIA_ROOT") or None,
            opensubtitles_key=env("TROPES_OPENSUBTITLES_KEY") or None,
            opensubtitles_user=env("TROPES_OPENSUBTITLES_USER") or None,
            opensubtitles_password=env("TROPES_OPENSUBTITLES_PASSWORD") or None,
        )
