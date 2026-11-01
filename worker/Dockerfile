# The model worker: Python 3.12, uv, no ffmpeg or Whisper (those belong to the media worker on the file host).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
# Data the worker keeps between runs; the compose file mounts /data.
ENV TROPES_SOURCES_DIR=/data/sources TROPES_TEXT_CACHE_DIR=/data/text TROPES_LOOKUP_CACHE_DIR=/data/cache/lookup
CMD ["uv", "run", "--no-sync", "tropes-worker", "run"]
