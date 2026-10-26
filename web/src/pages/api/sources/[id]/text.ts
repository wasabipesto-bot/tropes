import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { createHash } from 'node:crypto';
import type { APIRoute } from 'astro';
import { eq, sql } from 'drizzle-orm';
import { db } from '../../../../db';
import { localSource } from '../../../../db/schema';
import { textPath } from '../../../../lib/files';
import { badRequest, unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

/**
 * The media worker posts the text it extracted for one local source (subtitles rendered with
 * timestamps, a book's chapters). The file lives under data/texts; the row records the hash, the
 * word count and where the text came from. An empty text with a `none` reason marks the source as
 * tried and textless.
 */
export const POST: APIRoute = async ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const id = Number(params.id);
  const row = db.select().from(localSource).where(eq(localSource.id, id)).get();
  if (!row) return Response.json({ error: 'no such source' }, { status: 404 });
  const body = await request.json().catch(() => null);
  if (!body || typeof body.text !== 'string' || typeof body.source !== 'string') return badRequest('expected {text, source, meta?}');
  const meta = { ...JSON.parse(row.meta || '{}'), ...(body.meta ?? {}), textSource: body.source };
  if (body.text.trim()) {
    const path = textPath(id);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, body.text, 'utf8');
    meta.textHash = createHash('sha1').update(body.text).digest('hex');
    meta.words = body.text.split(/\s+/).filter(Boolean).length;
  } else {
    delete meta.textHash;
    meta.words = 0;
  }
  db.update(localSource).set({ meta: JSON.stringify(meta), indexedAt: sql`(datetime('now'))` }).where(eq(localSource.id, id)).run();
  return Response.json({ id, words: meta.words ?? 0 });
};
