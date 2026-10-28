"""One function to call the model: render a prompt file, ask for JSON matching a
pydantic schema, validate, retry once with the complaint, and keep the usage tally."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from openai import AsyncOpenAI, BadRequestError
from pydantic import BaseModel, ValidationError

from .settings import Settings

log = logging.getLogger("tropes_worker.llm")
PROMPTS = Path(__file__).parent / "prompts"
T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    model: str = ""
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, resp: Any) -> None:
        u = getattr(resp, "usage", None)
        self.calls += 1
        if u is None:
            return
        self.prompt_tokens += int(getattr(u, "prompt_tokens", 0) or 0)
        self.completion_tokens += int(getattr(u, "completion_tokens", 0) or 0)
        details = getattr(u, "prompt_tokens_details", None)
        self.cached_tokens += int(getattr(details, "cached_tokens", 0) or 0) if details else 0
        extra = getattr(u, "model_extra", None) or {}
        self.cost_usd += float(extra.get("cost") or 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "calls": self.calls,
            "promptTokens": self.prompt_tokens,
            "completionTokens": self.completion_tokens,
            "cachedTokens": self.cached_tokens,
            "costUsd": round(self.cost_usd, 6),
        }


@dataclass
class Prompt:
    name: str
    version: int
    body: str


_cache: dict[str, Prompt] = {}
# Live clients, so a job's loop can close them before it ends (otherwise their connections are torn down
# by the garbage collector on a closed loop, which asyncio logs as an error).
_live: list[LLM] = []


def load_prompt(name: str) -> Prompt:
    """A prompt file is optional `---\\nversion: N\\n---` frontmatter, then the template."""
    if name in _cache:
        return _cache[name]
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    version = 1
    m = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if line.strip().startswith("version:"):
                version = int(line.split(":", 1)[1].strip())
        text = text[m.end() :]
    p = Prompt(name=name, version=version, body=text.strip())
    _cache[name] = p
    return p


def render(name: str, variables: dict[str, Any]) -> str:
    body = load_prompt(name).body

    def sub(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        if key not in variables:
            raise KeyError(f"prompt {name} needs {{{{{key}}}}}")
        v = variables[key]
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1)

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", sub, body)


def _extract_json(s: str) -> str:
    s = s.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        s = m.group(1).strip()
    start = min([i for i in (s.find("{"), s.find("[")) if i >= 0], default=0)
    return s[start:]


@dataclass
class LLM:
    settings: Settings
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        if not self.settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.settings.openrouter_api_key,
            timeout=self.settings.call_timeout,
            max_retries=3,
            default_headers={"HTTP-Referer": "https://github.com/wasabipesto-bot/tropes", "X-Title": "Trope Log"},
        )
        self._sem: asyncio.Semaphore | None = None
        self._sem_loop: asyncio.AbstractEventLoop | None = None
        self.usage.model = self.settings.model
        self._schema_ok: dict[str, bool] = {}
        _live.append(self)

    async def aclose(self) -> None:
        if self in _live:
            _live.remove(self)
        await self._client.close()

    @staticmethod
    async def close_all() -> None:
        for llm in list(_live):
            await llm.aclose()

    async def complete(
        self,
        prompt: str,
        variables: dict[str, Any],
        schema: type[T],
        *,
        model: str | None = None,
        images: list[str] | None = None,
    ) -> T:
        """Render `prompt` with `variables`, get JSON back, validate as `schema`.
        `images` are base64 JPEGs shown with the prompt (contact sheets, frames)."""
        user = render(prompt, variables)
        system = load_prompt("system").body
        model = model or self.settings.model
        content: Any = user
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}} for b in images
            ]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        last_error = ""
        for attempt in range(2):
            raw = await self._call(messages, schema, model)
            try:
                return schema.model_validate_json(_extract_json(raw))
            except (ValidationError, ValueError) as e:
                last_error = str(e)[:1500]
                log.warning("prompt %s: bad JSON on attempt %d: %s", prompt, attempt + 1, last_error[:200])
                messages = messages + [
                    {"role": "assistant", "content": raw[:6000]},
                    {
                        "role": "user",
                        "content": f"That reply was not valid against the required JSON shape:\n{last_error}\nReply again with only the JSON object, nothing else.",  # noqa: E501
                    },
                ]
        raise ValueError(f"prompt {prompt}: model output failed validation twice: {last_error}")

    async def _call(self, messages: list[dict[str, Any]], schema: type[BaseModel], model: str) -> str:
        use_schema = self.settings.json_schema and self._schema_ok.get(model, True)
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": self.settings.temperature}
        extra: dict[str, Any] = {"usage": {"include": True}}
        if self.settings.reasoning in ("off", "none", "0", "false"):
            extra["reasoning"] = {"enabled": False}
        elif self.settings.reasoning in ("low", "medium", "high"):
            extra["reasoning"] = {"effort": self.settings.reasoning, "exclude": True}
        if use_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": False},
            }
            if self.settings.response_healing:
                extra["plugins"] = [{"id": "response-healing"}]
        async with self._semaphore():
            try:
                resp = await self._client.chat.completions.create(extra_body=extra, **kwargs)
            except BadRequestError as e:
                if not use_schema:
                    raise
                # This model or route rejects json_schema; fall back to prompt-only JSON for the rest of the run.
                log.warning("model %s rejected response_format (%s); continuing without it", model, str(e)[:120])
                self._schema_ok[model] = False
                kwargs.pop("response_format", None)
                extra.pop("plugins", None)
                resp = await self._client.chat.completions.create(extra_body=extra, **kwargs)
        self.usage.add(resp)
        choice = resp.choices[0]
        content = choice.message.content or ""
        if not content.strip():
            raise ValueError(f"empty reply (finish_reason={choice.finish_reason})")
        return content

    def _semaphore(self) -> asyncio.Semaphore:
        # A semaphore is bound to the loop that created it; jobs run in one loop, but be safe anyway.
        loop = asyncio.get_running_loop()
        if self._sem is None or self._sem_loop is not loop:
            self._sem = asyncio.Semaphore(self.settings.concurrency)
            self._sem_loop = loop
        return self._sem

    async def gather(self, coros: list[Any]) -> list[Any]:
        return await asyncio.gather(*coros)

    async def gather_safely(self, coros: list[Any], label: str = "item") -> tuple[list[Any], list[str]]:
        """Like gather, but an item whose model reply failed validation (or any other error) becomes None and a
        warning instead of killing the job; batches already posted stay posted."""
        results = await asyncio.gather(*coros, return_exceptions=True)
        out: list[Any] = []
        warnings: list[str] = []
        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                if isinstance(r, asyncio.CancelledError):
                    raise r
                log.warning("%s %d failed: %s", label, i, str(r)[:200])
                warnings.append(f"{label} {i} skipped: {str(r).splitlines()[0][:160]}")
                out.append(None)
            else:
                out.append(r)
        return out, warnings
