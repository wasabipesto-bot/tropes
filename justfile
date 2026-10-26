# Trope Log: a personal TVTropes-style catalogue built on a media log.
set shell := ["bash", "-cu"]

# Checkout location on remote hosts, for `just on <host> <recipe>`.
REPO_DIR := env("TROPES_REPO_DIR", "~/projects/tropes")
SITE := env("TROPES_SITE_URL", "http://127.0.0.1:4321")
DB := env("DATABASE_PATH", "web/data/tropes.db")
# rsync destination for off-host copies of the backups; empty skips the copy.
BACKUP_REMOTE := env("TROPES_BACKUP_REMOTE", "braize:tropes-backups")
BACKUP_KEEP := env("TROPES_BACKUP_KEEP", "14")

default:
    @just --list

# Install web (npm) and worker (uv) dependencies.
setup:
    cd web && npm ci --no-audit --no-fund
    cd worker && uv sync

# Serve the site locally with live reload. Pass a host to expose it: just dev 100.109.36.42
[working-directory('web')]
dev host="127.0.0.1":
    npm run dev -- --host {{host}}

# Build the site into web/dist.
[working-directory('web')]
build:
    npm run build

# Run the built site from web/dist (needs `just build`).
[working-directory('web')]
start:
    npm run start

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
[working-directory('web')]
db-generate name:
    npx drizzle-kit generate --name {{name}}

# Apply pending migrations to the configured database (the site also does this at startup).
[working-directory('web')]
db-migrate:
    npm run db:migrate

# Import a Notion CSV export: just import path/to/export.csv [--dry-run]
[working-directory('web')]
import file *flags:
    npx tsx scripts/import.ts {{file}} {{flags}}

# Load the seed tropes and instances from web/seed/ (skips anything already present).
[working-directory('web')]
seed *flags:
    npx tsx scripts/seed.ts {{flags}}

# Create a worker API token (printed once): just api-key ivory-worker
[working-directory('web')]
api-key name:
    npx tsx scripts/api-key.ts '{{name}}'

# Register text sources for works: just link-sources ../data/sources/sources.json  |  just link-sources "Lent" path.epub
[working-directory('web')]
link-sources *args:
    npx tsx scripts/link-sources.ts {{args}}

# Run the pipeline worker in the foreground (reads the repo .env).
[working-directory('worker')]
worker *flags:
    uv run tropes-worker run {{flags}}

# Score the scan against verified instances: just eval --trope dog-duo
[working-directory('worker')]
eval *flags:
    uv run tropes-worker eval {{flags}}

# Read the Notion Media Log once and hand the rows to the site (the worker loop also does this on a timer).
[working-directory('worker')]
sync-notion:
    uv run tropes-worker sync

# Resolve identities for a sample of the library and print the report; writes nothing: just lookup --sample 50
[working-directory('worker')]
lookup *flags:
    uv run tropes-worker lookup {{flags}}

# Report which works have files on the media disk; writes nothing: just media-match --root /data
[working-directory('worker')]
media-match *flags:
    uv run tropes-worker media match {{flags}}

# What to run on celebrimbor to set up the media worker (prints the commands; nothing is executed here).
setup-media:
    @echo 'curl -LsSf https://astral.sh/uv/install.sh | sh'
    @echo 'git clone https://github.com/wasabipesto-bot/tropes ~/projects/tropes && cd ~/projects/tropes/worker && uv sync'
    @echo 'printf "TROPES_SITE_URL=http://100.109.36.42:4321\nTROPES_API_TOKEN=<from just api-key celebrimbor>\nTROPES_MEDIA_ROOT=/data\nTROPES_OPENSUBTITLES_KEY=<key>\n" > ~/projects/tropes/.env'
    @echo 'mkdir -p ~/.config/systemd/user && cp ~/projects/tropes/ops/tropes-media-worker.service ~/.config/systemd/user/'
    @echo 'loginctl enable-linger $USER && systemctl --user daemon-reload && systemctl --user enable --now tropes-media-worker'

# Print a password hash for OWNER_PASSWORD_HASH: just hash-password 'secret'
[working-directory('web')]
hash-password password:
    npx tsx scripts/hash-password.ts '{{password}}'

# Snapshot the database and evidence files into backups/ and copy them off-host (VACUUM INTO, so the site keeps running).
backup:
    #!/usr/bin/env bash
    set -euo pipefail
    stamp=$(date -u +%Y%m%d-%H%M%S)
    mkdir -p backups
    rm -f "backups/tropes-${stamp}.db"
    sqlite3 "{{DB}}" "VACUUM INTO 'backups/tropes-${stamp}.db'"
    if [ -d web/data/evidence ]; then tar -czf "backups/evidence-${stamp}.tar.gz" -C web/data evidence; fi
    prune() { find backups -maxdepth 1 -name "$1" -printf '%T@ %p\n' | sort -rn | tail -n +$(( {{BACKUP_KEEP}} + 1 )) | cut -d' ' -f2- | xargs -r rm -f; }
    prune 'tropes-*.db'; prune 'evidence-*.tar.gz'
    echo "snapshot backups/tropes-${stamp}.db ($(du -h "backups/tropes-${stamp}.db" | cut -f1)), $(ls backups | wc -l) files kept locally"
    if [ -n "{{BACKUP_REMOTE}}" ]; then
        rsync -a --mkpath --delete backups/ "{{BACKUP_REMOTE}}/" && echo "copied to {{BACKUP_REMOTE}}"
    fi

# Build and start the containers.
up:
    docker compose up --build -d

# Stop the containers.
[confirm("Stop the site containers?")]
down:
    docker compose down

# Follow the site container's logs.
logs:
    docker compose logs -f --tail=100 web

# Ask the running site whether it is healthy.
health:
    curl -sf {{SITE}}/api/health && echo

# Ask the worker to ping the site.
[working-directory('worker')]
ping:
    uv run tropes-worker ping --site {{SITE}}

# `bash -lc` below so a `just` installed under ~/.cargo/bin is found by non-interactive ssh.

# Run a recipe on another host: just on shalash health
on host recipe *args:
    #!/usr/bin/env bash
    set -euo pipefail
    tty=""; [ -t 0 ] && tty="-t"
    # shellcheck disable=SC2086
    exec ssh $tty "{{host}}" "bash -lc 'cd {{REPO_DIR}} && just {{recipe}} {{args}}'"

# Pull main, rebuild and restart the containers, then check health. Run on the host.
[confirm("Pull main and redeploy the containers here?")]
deploy:
    git pull --ff-only
    docker compose up --build -d
    sleep 2
    just health
