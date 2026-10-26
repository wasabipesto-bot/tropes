import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import type { APIRoute } from 'astro';
import { eq } from 'drizzle-orm';
import { db } from '../../../../../db';
import { localSource } from '../../../../../db/schema';
import { sheetPath } from '../../../../../lib/files';
import { badRequest, unauthorized, workerAuthorized } from '../../../../../lib/worker-auth';

/** The media worker uploads contact sheet n (JPEG) for a video source; meta.sheets records how many it has. */
export const PUT: APIRoute = async ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const id = Number(params.id);
  const n = Number(params.n);
  const row = db.select().from(localSource).where(eq(localSource.id, id)).get();
  if (!row || !Number.isInteger(n) || n < 0 || n > 20) return badRequest('no such source or sheet number');
  const buf = Buffer.from(await request.arrayBuffer());
  if (buf.length < 1000 || buf.length > 3_000_000 || buf[0] !== 0xff || buf[1] !== 0xd8) return badRequest('expected a JPEG under 3 MB');
  const path = sheetPath(id, n);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, buf);
  const meta = JSON.parse(row.meta || '{}');
  meta.sheets = Math.max(Number(meta.sheets ?? 0), n + 1);
  db.update(localSource).set({ meta: JSON.stringify(meta) }).where(eq(localSource.id, id)).run();
  return Response.json({ id, sheets: meta.sheets });
};
