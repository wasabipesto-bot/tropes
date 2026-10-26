# Phase 6: public hardening

Status 2026-10-26: the owner said "seems straightforward, go ahead"; this
page records the decisions I am building to and the three questions that
change details. Items are the ROADMAP's Phase 6 list.

## Decisions

1. **Evidence caps** (defaults from 2026-10-19, all env-configurable):
   quotes up to `TROPES_QUOTE_WORDS` (100), up to
   `TROPES_FRAMES_PER_WORK_TROPE` (10) frames per work per trope, clips up
   to `TROPES_CLIP_SECONDS` (30, already trimmed at extraction). Enforced
   with a `public` flag on evidence, set at insert and recomputed per work
   and trope whenever evidence changes: the 11th frame and an over-long
   quote stay in the database and visible to the owner (marked "owner
   only"), never deleted. Anonymous visitors do not get the row, and the
   file route answers 404 for a non-public file.
2. **Rate limiting**: an Astro middleware with a token bucket per client
   address, in memory (one process): search 30/min, anonymous page views
   120/min, `/api/v1` 60/min, the worker routes exempt (they carry a key).
   429 with `Retry-After`. Behind a proxy the address comes from
   `CF-Connecting-IP` or the last `X-Forwarded-For` hop only when
   `TROPES_TRUSTED_PROXY=1`.
3. **robots and OG**: `robots.txt` allows everything except `/api`,
   `/review`, `/metadata`, `/update`, `/jobs`, `/sheets`, `/evidence/pending`
   and `/login`; every public page gets `og:title`, `og:description`, a
   canonical URL and, for works, `og:image` (the 300 px poster). Absolute
   URLs need `SITE_ORIGIN` (question 1).
4. **Cache headers**: evidence and poster files immutable (done for
   evidence); anonymous HTML `public, max-age=60`; owner pages `private,
   no-store`.
5. **Passkeys**: WebAuthn through `@simplewebauthn/server`; the owner
   registers a passkey from an account page while logged in with the
   password, then the login page offers "Use a passkey" with the password
   as the fallback. `rpID` is the public hostname (question 1). I cannot
   drive a browser here, so the ceremony is unit-tested against the
   library's vectors and tried by the owner on a phone.
6. **Backups**: `just backup` makes a consistent SQLite snapshot (`VACUUM
   INTO`) and rsyncs it with `data/evidence`, `data/posters` and
   `data/sources` to the Hetzner storage box the owner already uses
   (braize, ssh port 23), keeping 14 daily and 8 weekly; a systemd timer
   runs it nightly on the host. Sheets, texts and the lookup cache are
   regenerable and are not backed up (question 2).
7. **Narrow screens**: the three-column rows collapse to one column under
   720 px, the margin column moves below the entry, controls get full-width
   tap targets. Checked by reasoning here, by eye on the owner's phone.
8. **Tumblr mention count**: stays the link it already is ("wasabipesto's
   Tumblr posts mentioning …"); no count until relevance filtering exists.

## Questions

1. **Hostname and hosting.** What will the public URL be, and does it sit
   behind Cloudflare or a reverse proxy on the host? This sets `SITE_ORIGIN`
   for OG and canonical links, the passkey `rpID`, and which header the rate
   limiter trusts.
2. **Backup destination.** braize over rsync as above, or R2? And should the
   extracted texts go too (cheap, but regenerable in a day)?
3. **Rate numbers.** 30 searches, 120 pages and 60 API calls a minute per
   address: fine, or stricter?

## Order

Caps and the public flag → middleware (limits, cache headers) → robots and
OG → backups → passkeys → the narrow-screen pass. Each lands as its own
commit; nothing here spends model money.
