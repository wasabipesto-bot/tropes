import type { APIRoute } from 'astro';
import { and, eq, inArray } from 'drizzle-orm';
import { db } from '../../../db';
import { localSource } from '../../../db/schema';
import { sourcesBody } from '../../../lib/jobs/schemas';
import { badRequest, unauthorized, workerAuthorized } from '../../../lib/worker-auth';

/**
 * The media worker reports what it found on the disk for some works: one row per episode file, film
 * file or Calibre book. Disk rows for those works are replaced; texts the owner linked by hand (kind
 * text) are left alone. Rows keep their ids when the path is unchanged, so extracted text stays attached.
 */
export const POST: APIRoute = async ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const parsed = sourcesBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest(parsed.error.message);
  let kept = 0, added = 0, removed = 0;
  db.transaction((tx) => {
    for (const w of parsed.data.works) {
      const existing = tx.select().from(localSource).where(and(eq(localSource.mediaId, w.mediaId), inArray(localSource.kind, ['video', 'audio', 'book', 'subtitle']))).all();
      const wantedPaths = new Set(w.sources.map((s) => s.path));
      const stale = existing.filter((e) => !wantedPaths.has(e.path));
      if (stale.length) tx.delete(localSource).where(inArray(localSource.id, stale.map((e) => e.id))).run();
      removed += stale.length;
      for (const s of w.sources) {
        const row = existing.find((e) => e.path === s.path);
        if (row) {
          tx.update(localSource).set({ kind: s.kind, label: s.label, meta: JSON.stringify(s.meta) }).where(eq(localSource.id, row.id)).run();
          kept++;
        } else {
          tx.insert(localSource).values({ mediaId: w.mediaId, kind: s.kind, path: s.path, label: s.label, meta: JSON.stringify(s.meta) }).run();
          added++;
        }
      }
    }
  });
  return Response.json({ kept, added, removed });
};
