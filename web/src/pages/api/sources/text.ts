import type { APIRoute } from 'astro';
import { and, eq } from 'drizzle-orm';
import { db } from '../../../db';
import { localSource } from '../../../db/schema';
import { textLinkBody } from '../../../lib/jobs/schemas';
import { badRequest, unauthorized, workerAuthorized } from '../../../lib/worker-auth';

/** The model worker links a text it fetched itself (a Fandom transcript, plan T12): one row per work and path. */
export const POST: APIRoute = async ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const parsed = textLinkBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest(parsed.error.message);
  const { mediaId, path, label } = parsed.data;
  const row = db.select().from(localSource).where(and(eq(localSource.mediaId, mediaId), eq(localSource.path, path))).get();
  if (row) {
    db.update(localSource).set({ label }).where(eq(localSource.id, row.id)).run();
    return Response.json({ id: row.id, created: false });
  }
  const created = db.insert(localSource).values({ mediaId, kind: 'text', path, label }).returning().get();
  return Response.json({ id: created.id, created: true });
};
