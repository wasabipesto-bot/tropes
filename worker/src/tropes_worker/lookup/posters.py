"""Posters: download the first candidate that is a usable image, make the three WebP sizes."""

from __future__ import annotations

import logging
import re
from io import BytesIO

from PIL import Image

from .http import Fetcher

log = logging.getLogger("tropes_worker.lookup.posters")

SIZES = (900, 300, 50)
QUALITY = {900: 82, 300: 80, 50: 70}
MIN_WIDTH = 200


WIKIMEDIA_THUMB = re.compile(r"^(https://upload\.wikimedia\.org/wikipedia/[a-z]+/)thumb/([^/]+/[^/]+/[^/]+)/\d+px-[^/]+$")


def fetch_url(url: str) -> str:
    """A Wikimedia thumbnail link (often 220 px, and 400 when stale) is fetched as its full-size original."""
    m = WIKIMEDIA_THUMB.match(url)
    return f"{m.group(1)}{m.group(2)}" if m else url


def prepare(f: Fetcher, urls: list[str]) -> tuple[str, dict[int, bytes]] | None:
    """Try the URLs in order; return (source url as given, {width: webp bytes}) for the first real image."""
    for url in urls:
        data = f.get_bytes(fetch_url(url))
        if not data:
            continue
        try:
            img = Image.open(BytesIO(data))
            img.load()
        except Exception as e:  # noqa: BLE001 - any undecodable image just means "try the next"
            log.info("poster %s: not an image (%s)", url, type(e).__name__)
            continue
        if img.width < MIN_WIDTH:
            continue
        return url, resize_all(img)
    return None


def resize_all(img: Image.Image) -> dict[int, bytes]:
    """Width-constrained copies; square art stays square. An original narrower than 900 keeps its width."""
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
    out: dict[int, bytes] = {}
    for w in SIZES:
        copy = img if img.width <= w else img.resize((w, max(1, round(img.height * w / img.width))), Image.LANCZOS)
        buf = BytesIO()
        copy.save(buf, "WEBP", quality=QUALITY[w], method=4)
        out[w] = buf.getvalue()
    return out
