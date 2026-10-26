import { createReadStream, statSync } from 'node:fs';
import { Readable } from 'node:stream';
import type { APIRoute } from 'astro';
import { evidencePath } from '../../lib/files';

const TYPES: Record<string, string> = { webp: 'image/webp', mp4: 'video/mp4', jpg: 'image/jpeg' };

/** Public evidence files: data/evidence/<instance>/<evidence>.webp|mp4. Pending files for the review page are served to the owner under pending/. */
export const GET: APIRoute = ({ params, locals, request }) => {
  const rel = params.path ?? '';
  if (!/^(pending\/\d+\/)?\d+\/?[\w.-]+\.(webp|mp4|jpg)$/.test(rel) || rel.includes('..')) return new Response(null, { status: 404 });
  if (rel.startsWith('pending/') && !locals.owner) return new Response(null, { status: 404 });
  const path = evidencePath(rel);
  let size: number;
  try { size = statSync(path).size; } catch { return new Response(null, { status: 404 }); }
  const ext = rel.split('.').pop() ?? '';
  const range = request.headers.get('range');
  if (range && ext === 'mp4') {
    const m = /bytes=(\d*)-(\d*)/.exec(range);
    const start = m && m[1] ? Number(m[1]) : 0;
    const end = m && m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
    return new Response(Readable.toWeb(createReadStream(path, { start, end })) as ReadableStream, {
      status: 206,
      headers: { 'content-type': TYPES[ext], 'content-range': `bytes ${start}-${end}/${size}`, 'content-length': String(end - start + 1), 'accept-ranges': 'bytes' },
    });
  }
  return new Response(Readable.toWeb(createReadStream(path)) as ReadableStream, {
    headers: { 'content-type': TYPES[ext] ?? 'application/octet-stream', 'content-length': String(size), 'accept-ranges': 'bytes', 'cache-control': rel.startsWith('pending/') ? 'no-store' : 'public, max-age=31536000, immutable' },
  });
};
