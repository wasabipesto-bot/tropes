import { createReadStream, statSync } from 'node:fs';
import { Readable } from 'node:stream';
import type { APIRoute } from 'astro';
import { POSTER_SIZES, posterPath, type PosterSize } from '../../lib/files';

/** Serve data/posters/<id>-<size>.webp. Pages add ?v=<mtime> so the long cache header is safe. */
export const GET: APIRoute = ({ params }) => {
  const m = /^(\d+)-(\d+)\.webp$/.exec(params.file ?? '');
  if (!m || !(POSTER_SIZES as readonly number[]).includes(Number(m[2]))) return new Response(null, { status: 404 });
  const path = posterPath(Number(m[1]), Number(m[2]) as PosterSize);
  let size: number;
  try { size = statSync(path).size; } catch { return new Response(null, { status: 404 }); }
  return new Response(Readable.toWeb(createReadStream(path)) as ReadableStream, {
    headers: { 'content-type': 'image/webp', 'content-length': String(size), 'cache-control': 'public, max-age=31536000, immutable' },
  });
};
