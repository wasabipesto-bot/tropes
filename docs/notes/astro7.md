# Astro 7.x / Node adapter / Drizzle+better-sqlite3 — reference notes

Verified against docs.astro.build and orm.drizzle.team on 2026-10-19, against astro
7.4.1, @astrojs/node 11.1.9, better-sqlite3 13.0.3, drizzle-orm 0.45.4, drizzle-kit
0.31.11, Node 24. UNVERIFIED = not confirmed from a fetched doc page this pass.

---

## 1. astro.config: output, Node adapter, checkOrigin, site, vite

`output` is now only `'static' | 'server'` (default `'static'`). `'hybrid'` was
removed in v5 — forget the old three-mode model.

```js
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }), // or 'middleware'
  site: 'https://www.my-site.dev',
  security: { checkOrigin: true }, // default
  vite: { ssr: { external: ['better-sqlite3'] } }, // only if Vite tries to SSR-bundle the native addon
});
```

- Node adapter `mode: 'standalone'` = self-contained server (`./dist/server/
  entry.mjs`, run with `node ./dist/server/entry.mjs`), serves static + SSR itself.
  `mode: 'middleware'` exports a `handler` to mount on your own Express/Fastify/etc.
  server; you serve static files yourself.
- Other node() options: `staticHeaders` (bool, default false), `bodySizeLimit`
  (bytes, default 1 GB; 0/Infinity disables), `experimentalDisableStreaming`.
- `security.checkOrigin` default `true`: compares `Sec-Fetch-Site` (fallback
  `Origin`) header to the request URL, only for on-demand pages and only for unsafe
  methods (POST/PATCH/PUT/DELETE) with content-type empty or one of
  `application/x-www-form-urlencoded`/`multipart/form-data`/`text/plain`. Mismatch →
  403, nothing runs. `security.allowedDomains` (5.14.2+) whitelists reverse-proxy
  domains.
- `site` just sets the canonical/sitemap URL; not required for SSR correctness.

Doc: https://docs.astro.build/en/reference/configuration-reference/
Doc: https://docs.astro.build/en/guides/integrations-guide/node/

---

## 2. Middleware

File: `src/middleware.ts` (or `src/middleware/index.ts`), export `onRequest`.

```ts
import { defineMiddleware, sequence } from 'astro:middleware';

const auth = defineMiddleware((context, next) => {
  context.locals.user = { id: 1, name: 'John' };
  return next();
});

export const onRequest = sequence(auth /*, more, in order */);
```

`context.locals` is the per-request bag shared middleware → endpoints → `.astro`
pages (`Astro.locals` there) — put the session-resolved user here. Type it in
`src/env.d.ts`:

```ts
declare namespace App {
  interface Locals { user: { id: number; name: string } | null; }
}
```

`sequence(a, b, c)` chains middlewares in order; each calls `next()`, responses
unwind back in reverse.

Doc: https://docs.astro.build/en/guides/middleware/

---

## 3. Cookies API

`Astro.cookies` in `.astro` files; `context.cookies` identically in middleware,
endpoints, Actions.

```ts
const token = Astro.cookies.get('token'); // AstroCookie | undefined
Astro.cookies.set('session', sessionId, {
  httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge: 60 * 60 * 24 * 7,
});
Astro.cookies.has('session');
Astro.cookies.delete('session', { path: '/' });
```

- `get(key, opts?)` → `AstroCookie` with `.value` plus `.json()/.number()/.boolean()`.
- `AstroCookieSetOptions`: `httpOnly`, `secure`, `sameSite` (`boolean|'lax'|'none'|
  'strict'`), `path`, `maxAge` (seconds), `domain`, `expires` (Date), `encode`.
- `delete()` just expires the cookie.

Doc: https://docs.astro.build/en/reference/api-reference/

---

## 4. Actions

File `src/actions/index.ts`, export a `server` object.

```ts
import { defineAction, ActionError } from 'astro:actions';
import { z } from 'astro/zod';

export const server = {
  login: defineAction({
    accept: 'form', // omit for JSON (default)
    input: z.object({ password: z.string() }),
    handler: async (input, context) => {
      // context: locals, cookies, request, site, url — same shape as APIContext
      if (input.password !== 'correct') {
        throw new ActionError({ code: 'UNAUTHORIZED', message: 'Bad password' });
      }
      context.cookies.set('session', makeSessionId(), { httpOnly: true, secure: true });
      return { ok: true };
    },
  }),
};
```

Client call: `const { data, error } = await actions.login({ password: 'x' })` (import
`actions` from `astro:actions`).

Progressive-enhancement plain form (no JS):

```astro
<form method="POST" action={actions.login}>
  <input type="password" name="password" />
  <button>Log in</button>
</form>
```

Read the result + redirect on the receiving page:

```ts
const result = Astro.getActionResult(actions.login);
if (result && !result.error) return Astro.redirect('/dashboard');
```

- Errors: `throw new ActionError({ code, message })`; `isInputError(error)` narrows
  to Zod validation errors with `.fields` keyed by field name.
- CSRF/origin: not called out on the Actions doc page itself, but form-posted
  Actions go through POST with a form content-type, so the default
  `security.checkOrigin: true` (§1) already covers them — no separate CSRF system.
- v6 removed `rewrite()` from the Actions context — don't reach for it.

Doc: https://docs.astro.build/en/guides/actions/

---

## 5. Sessions (`Astro.session`) — stable, but probably not the right fit here

Stable (non-experimental) since `astro@5.7.0`. The Node adapter auto-configures a
default driver — no `session.driver` config needed to make it work. Example shape
for a driver override (different adapter, shown for reference):

```js
import { defineConfig, sessionDrivers } from 'astro/config';
export default defineConfig({
  session: { driver: sessionDrivers.lruCache({ max: 800 }) },
});
```

Caveats from docs: driver config is resolved at **build time** and any env vars it
uses get inlined — can't override at runtime unless driver setup lives in a
separate entrypoint reading env at runtime. Also: sessions unsupported in edge
middleware (not relevant for Node/standalone).

Fit assessment: `Astro.session` is a generic KV session store over a pluggable
driver, not an auth-specific primitive. For a single-owner password login, a
**hand-rolled `sessions` table via Drizzle** is likely simpler: same DB/transaction
as the rest of the app, full control of schema (expiry, revoke-all), no separate
driver/build-time-inlining caveat, trivially inspectable. `Astro.session` wins on
zero plumbing and an idiomatic `.get/.set` API, but for this app's one login flow a
dedicated table is less indirection.

Doc: https://docs.astro.build/en/guides/sessions/

---

## 6. Endpoints (API routes)

```ts
// src/pages/api/users/[id].ts
import type { APIRoute } from 'astro';

export const GET = (async ({ params }) => {
  return new Response(JSON.stringify({ id: params.id }));
}) satisfies APIRoute;

export const POST = (async ({ request }) => {
  const body = await request.json();
  // or: const form = await request.formData(); const file = form.get('field');
  return new Response(JSON.stringify({ received: body }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}) satisfies APIRoute;
```

- Export `GET`/`POST`/`PUT`/`DELETE`/`PATCH`/`HEAD`/`ALL`, typed `APIRoute`.
- JSON: `request.json()`. Multipart/form: `request.formData()` → `FormData`.
- Dynamic params from filename (`[id].ts`) via `params.id`.
- **`export const prerender = false` is NOT required under `output: 'server'`** —
  everything is on-demand by default there. It only matters per-route under
  `'static'` output.

Doc: https://docs.astro.build/en/guides/endpoints/

---

## 7. Client `<script>` tags and script-only islands

```astro
---
const message = 'hi from the server';
---
<button id="greet" data-message={message}>Greet</button>

<script>
  // processed: TS allowed, imports bundled, deduped, auto type="module"
  document.getElementById('greet')?.addEventListener('click', (e) => {
    const msg = (e.currentTarget as HTMLElement).dataset.message;
    alert(msg);
  });
</script>

<script is:inline>
  console.log('raw inline script, unprocessed'); // no TS, no import resolution
</script>
```

- Default script (no attrs but `src`): Astro bundles imports, allows TS, dedupes
  repeated instances, auto `type="module"`, may inline small scripts.
- `is:inline` opts out of all that (byte-for-byte output); also required for any
  `<script src="...">` pointing at an external URL or a `public/`-served path.
- Passing server data in: the docs demonstrate `data-*` attributes read back via
  `element.dataset` (shown above), not a dedicated directive in the pages fetched
  this pass. `define:vars` existed in older Astro — treat as **UNVERIFIED** for 7.x
  until re-checked; prefer the `data-*` pattern shown above.
- `client:*` directives (`client:load`, `client:visible`, …) apply **only to UI
  framework components** (React/Vue/Svelte/etc.) — meaningless on a plain `<script>`
  or a no-framework island; such a script just runs once loaded.

Doc: https://docs.astro.build/en/guides/client-side-scripts/

---

## 8. Fonts

The `fonts` config array showed no experimental banner on the fetched page, but
confirm against the 7.4.1 changelog before treating it as fully stable — mark
**UNVERIFIED-STRONG**.

Google Fonts via the Fontsource provider (downloaded/optimized onto your own site,
not Google's CDN):

```js
import { defineConfig, fontProviders } from 'astro/config';
export default defineConfig({
  fonts: [{ provider: fontProviders.fontsource(), name: 'Source Serif 4', cssVariable: '--font-source-serif-4' }],
});
```

```astro
---
import { Font } from 'astro:assets';
---
<head><Font cssVariable="--font-source-serif-4" /></head>
```

Fully self-hosted woff2, no provider/network:

```js
export default defineConfig({
  fonts: [{
    provider: fontProviders.local(), name: 'CustomFont', cssVariable: '--font-custom',
    options: { variants: [{ src: ['./src/assets/fonts/font.woff2'], weight: 'normal', style: 'normal' }] },
  }],
});
```

For Source Serif 4: `fontProviders.fontsource()` is the documented route and *is*
effectively self-hosting (Astro serves the files from your own site with automatic
subsetting/preload optimization). Dropping a `.woff2` under `public/` with hand-
written `@font-face` is a valid simpler alternative but loses that optimization.

Doc: https://docs.astro.build/en/guides/fonts/

---

## 9. Environment variables (`astro:env`)

```js
import { defineConfig, envField } from 'astro/config';
export default defineConfig({
  env: {
    schema: {
      SESSION_SECRET: envField.string({ context: 'server', access: 'secret' }),
      PORT: envField.number({ context: 'server', access: 'public', default: 4321 }),
    },
  },
});
```

```ts
import { SESSION_SECRET } from 'astro:env/server'; // server-side only
```

- `context`: `'server'` or `'client'` (bundled to client too). `access`: `'public'`
  or `'secret'` (secrets never bundled client-side).
- `getSecret(name)` from `astro:env/server` for dynamic/runtime lookups.
- Legacy `import.meta.env.MY_VAR` still works but has no schema validation; per the
  v6 upgrade guide, `import.meta.env` values are now always inlined as-is with no
  type coercion.

Doc: https://docs.astro.build/en/guides/environment-variables/

---

## 10. Drizzle ORM + better-sqlite3

```ts
import { drizzle } from 'drizzle-orm/better-sqlite3';
import Database from 'better-sqlite3';

const sqlite = new Database('sqlite.db');
export const db = drizzle({ client: sqlite }); // shorthand drizzle(sqlite) also documented
```

```ts
import { int, sqliteTable, text } from 'drizzle-orm/sqlite-core';
export const usersTable = sqliteTable('users_table', {
  id: int().primaryKey({ autoIncrement: true }),
  name: text().notNull(),
});
```

`drizzle.config.ts`:

```ts
import { defineConfig } from 'drizzle-kit';
export default defineConfig({
  dialect: 'sqlite',
  schema: './src/schema.ts',
  out: './drizzle',
  dbCredentials: { url: 'sqlite.db' },
});
```

drizzle-kit CLI (0.31.11): `generate` (diff schema → new SQL migration file),
`migrate` (CLI command applying pending `.sql` files — distinct from the
programmatic `migrate()` below), plus `push`, `pull`, `studio`, `check`.

Running migrations at startup:

```ts
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { migrate } from 'drizzle-orm/better-sqlite3/migrator';
import Database from 'better-sqlite3';

const sqlite = new Database('sqlite.db');
const db = drizzle({ client: sqlite });
await migrate(db, { migrationsFolder: './drizzle' });
```

**FTS5**: no schema-builder support for `CREATE VIRTUAL TABLE ... USING fts5(...)`.
Documented path is a custom migration:

```bash
drizzle-kit generate --custom --name=create-fts5-index
```

then hand-edit the generated empty `.sql` file:

```sql
CREATE VIRTUAL TABLE posts_fts USING fts5(title, body, content='posts', content_rowid='id');
```

It then runs through the normal `migrate()`/`drizzle-kit migrate` pipeline. Query
FTS5 via raw `sql` template (`db.all(sql\`...\`)`/`db.execute(sql\`...\`)`) — no typed
query-builder support for FTS5 match syntax.

Doc: https://orm.drizzle.team/docs/sqlite/get-started-sqlite
Doc: https://orm.drizzle.team/docs/drizzle-config-file
Doc: https://orm.drizzle.team/docs/migrations
Doc: https://orm.drizzle.team/docs/kit-custom-migrations
Doc: https://orm.drizzle.team/docs/kit-overview

---

## 11. Testing

```ts
// vitest.config.ts
/// <reference types="vitest/config" />
import { getViteConfig } from 'astro/config';
export default getViteConfig({ test: { /* options */ } });
```

Docs recommend Vitest; `getViteConfig()` loads your real astro.config so tests share
aliases/plugins. For rendering `.astro` components directly, docs show the
(experimentally-prefixed) Container API:

```ts
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { expect, test } from 'vitest';
import Card from '../src/components/Card.astro';

test('renders card', async () => {
  const container = await AstroContainer.create();
  const result = await container.renderToString(Card, { slots: { default: 'content' } });
  expect(result).toContain('content');
});
```

Testing Actions/endpoints directly: **UNVERIFIED / not documented** on the testing
page. In practice both are plain async functions importable into Vitest with a
hand-built `context`/`APIContext`-shaped object, but this isn't an officially
prescribed pattern.

Doc: https://docs.astro.build/en/guides/testing/

---

## 12. Watch out — defaults/behaviors a pre-6 developer would get wrong

- `output: 'hybrid'` is gone (merged into `'static'` in v5); only `'static'|'server'`
  exist. Opt a static-mode route into SSR per-route with `prerender = false`.
- `security.checkOrigin` defaults `true` since v5.0 — 403s cross-origin
  POST/PUT/PATCH/DELETE with form-ish content-type on-demand, including Actions.
- Node floor is 22.12.0 as of v6 (Node 24 here is fine, don't assume 18/20).
- `@astrojs/db` removed entirely in v7 — Drizzle/better-sqlite3/node:sqlite are the
  replacement path.
- Legacy Content Collections API removed in v6, no back-compat — not used here but
  trips up old tutorials. `<ViewTransitions />` → `<ClientRouter />`. `Astro.glob()`
  → `import.meta.glob()`. `rewrite()` removed from Actions context. All v6.
- CommonJS config files (`.cjs`/`.cts`) unsupported since v6.
- Zod 4 landed with v6 — `z.string().email()`-style validators deprecated for
  `z.email()`; matters since Actions' `input` is a Zod schema.
- `compressHTML` default `true` → `'jsx'` in v7 (different whitespace rules).
  Markdown default processor also changed in v7; `@astrojs/markdown-remark` no
  longer installed by default.
- `src/fetch.ts` is a reserved filename as of v7 (advanced routing).
- Session `test` driver removed in v6; driver config is now object-shaped.
- `i18n.routing.redirectToDefaultLocale` now defaults `false` in v6 — irrelevant
  unless i18n routing is added.

Doc: https://docs.astro.build/en/guides/upgrade-to/v7/
Doc: https://docs.astro.build/en/guides/upgrade-to/v6/
