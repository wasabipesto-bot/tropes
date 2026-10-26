import { createReadStream, statSync } from 'node:fs';
import { Readable } from 'node:stream';
import type { APIRoute } from 'astro';
import { sheetPath } from '../../lib/files';

/** Contact sheets, owner-only: the pictures the visual notes were read from (diagnostics on the dossier page). */
export const GET: APIRoute = ({ params, locals }) => {
  const m = /^(\d+)-(\d+)\.jpg$/.exec(params.file ?? '');
  if (!m || !locals.owner) return new Response(null, { status: 404 });
  const path = sheetPath(Number(m[1]), Number(m[2]));
  let size: number;
  try { size = statSync(path).size; } catch { return new Response(null, { status: 404 }); }
  return new Response(Readable.toWeb(createReadStream(path)) as ReadableStream, { headers: { 'content-type': 'image/jpeg', 'content-length': String(size), 'cache-control': 'private, max-age=3600' } });
};
