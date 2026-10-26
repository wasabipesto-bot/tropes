import { createReadStream, statSync } from 'node:fs';
import { Readable } from 'node:stream';
import type { APIRoute } from 'astro';
import { eq } from 'drizzle-orm';
import { db } from '../../../../db';
import { localSource } from '../../../../db/schema';
import { textPath } from '../../../../lib/files';
import { unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

/** The extracted text of one local source, for the worker that reads for the model. */
export const GET: APIRoute = ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const id = Number(params.id);
  const row = db.select().from(localSource).where(eq(localSource.id, id)).get();
  if (!row) return Response.json({ error: 'no such source' }, { status: 404 });
  const path = textPath(id);
  let size: number;
  try { size = statSync(path).size; } catch { return Response.json({ error: 'no text' }, { status: 404 }); }
  return new Response(Readable.toWeb(createReadStream(path)) as ReadableStream, { headers: { 'content-type': 'text/plain; charset=utf-8', 'content-length': String(size) } });
};
