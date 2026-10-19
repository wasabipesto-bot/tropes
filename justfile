# Trope Log: a personal TVTropes-style catalogue built on a media log.
set shell := ["bash", "-cu"]

# Checkout location on remote hosts, for `just on <host> <recipe>`.
REPO_DIR := env("TROPES_REPO_DIR", "~/projects/tropes")
SITE := env("TROPES_SITE_URL", "http://127.0.0.1:4321")

default:
    @just --list

# Install web (npm) and worker (uv) dependencies.
setup:
    cd web && npm ci --no-audit --no-fund
    cd worker && uv sync

# Serve the site locally with live reload.
dev:
    cd web && npm run dev -- --host 127.0.0.1

# Build the site into web/dist.
build:
    cd web && npm run build

# Run the built site from web/dist (needs `just build`).
start:
    cd web && npm run start

# Type-check the site and lint the worker.
lint:
    cd web && npm run check
    cd worker && uv run ruff check .

# Run every test suite.
test:
    cd web && npm test
    cd worker && uv run pytest -q

# Lint, test and build: what CI runs.
ci: lint test build

# Create a new SQL migration from schema changes: just db-generate add-tropes
db-generate name:
    cd web && npx drizzle-kit generate --name {{name}}

# Apply pending migrations to the configured database (the site also does this at startup).
db-migrate:
    cd web && npm run db:migrate

# Import a Notion CSV export into the database: just import path/to/export.csv [--dry-run]
import file *flags:
    cd web && npx tsx scripts/import.ts {{file}} {{flags}}

# Build and start the containers.
up:
    docker compose up --build -d

# Stop the containers.
down:
    docker compose down

# Follow the site container's logs.
logs:
    docker compose logs -f --tail=100 web

# Ask the running site whether it is healthy.
health:
    curl -sf {{SITE}}/api/health && echo

# Ask the worker to ping the site.
ping:
    cd worker && uv run tropes-worker ping --site {{SITE}}

# Run a recipe on another host: just on ivory health
# `bash -lc` so a `just` installed under ~/.cargo/bin is found by non-interactive ssh.
on host recipe *args:
    #!/usr/bin/env bash
    set -euo pipefail
    tty=""; [ -t 0 ] && tty="-t"
    # shellcheck disable=SC2086
    exec ssh $tty "{{host}}" "bash -lc 'cd {{REPO_DIR}} && just {{recipe}} {{args}}'"

# Pull main, rebuild and restart the containers, then check health. Run on the host.
deploy:
    git pull --ff-only
    docker compose up --build -d
    sleep 2
    just health
