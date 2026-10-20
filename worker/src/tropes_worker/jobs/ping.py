"""Round-trip check: progress twice, return an empty result."""

from __future__ import annotations

from typing import Any

from ..runner import Context


def run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    ctx.progress(0, 2, "pong")
    ctx.progress(2, 2, "pong")
    return {"summary": {"pong": True, "payload": payload}}
