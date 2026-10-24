import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import type { APIRoute } from 'astro';
import { eq } from 'drizzle-orm';
import { db } from '../../../../db';
import { media } from '../../../../db/schema';
import { POSTER_SIZES, posterPath } from '../../../../lib/files';
import { placePoster } from '../../../../lib/metadata';
import { badRequest, unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

const MAX_BYTES = 6_000_000;
const WEBP = Buffer.from('RIFF');

/**
 * The worker uploads a poster as three WebP files (900, 300 and 50 px wide) in one multipart
 * request: fields p900, p300, p50 and `source` (the URL it came from). With `pending=1` the files
 * wait in data/posters/pending until the lookup is committed; otherwise they go live at once.
 */
export const POST: APIRoute = async ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const id = Number(params.id);
  if (!db.select({ id: media.id }).from(media).where(eq(media.id, id)).get()) return Response.json({ error: 'no such media' }, { status: 404 });
  const form = await request.formData().catch(() => null);
  if (!form) return badRequest('expected multipart form data');
  const source = String(form.get('source') ?? '');
  const pending = form.get('pending') === '1';
  if (!source) return badRequest('source is required');
  let written = 0;
  for (const size of POSTER_SIZES) {
    const file = form.get(`p${size}`);
    if (!(file instanceof File)) continue;
    const buf = Buffer.from(await file.arrayBuffer());
    if (buf.length === 0 || buf.length > MAX_BYTES) return badRequest(`p${size}: bad size ${buf.length}`);
    if (!buf.subarray(0, 4).equals(WEBP) || buf.subarray(8, 12).toString() !== 'WEBP') return badRequest(`p${size}: not a WebP file`);
    const path = posterPath(id, size, pending);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, buf);
    written++;
  }
  if (written === 0) return badRequest('no poster files');
  if (!pending) placePoster(db, id, source);
  return Response.json({ written, pending });
};
