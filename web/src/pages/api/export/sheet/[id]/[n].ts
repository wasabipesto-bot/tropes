import { createReadStream, statSync } from 'node:fs';
import { Readable } from 'node:stream';
import type { APIRoute } from 'astro';
import { db } from '../../../../../db';
import { sheetPath } from '../../../../../lib/files';
import { unauthorized, workerAuthorized } from '../../../../../lib/worker-auth';

/** A contact sheet for the model worker to read. */
export const GET: APIRoute = ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const path = sheetPath(Number(params.id), Number(params.n));
  let size: number;
  try { size = statSync(path).size; } catch { return Response.json({ error: 'no sheet' }, { status: 404 }); }
  return new Response(Readable.toWeb(createReadStream(path)) as ReadableStream, { headers: { 'content-type': 'image/jpeg', 'content-length': String(size) } });
};
