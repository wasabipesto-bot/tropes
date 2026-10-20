import type { APIRoute } from 'astro';
import { db } from '../../../db';
import { dossier } from '../../../db/schema';
import { storeDossiers } from '../../../lib/jobs/queue';
import { dossiersBody } from '../../../lib/jobs/schemas';
import { badRequest, unauthorized, workerAuthorized } from '../../../lib/worker-auth';

/** Every dossier, bodies included, for a scan. */
export const GET: APIRoute = ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const rows = db.select().from(dossier).all().map((d) => ({ ...d, body: JSON.parse(d.body) }));
  return Response.json({ dossiers: rows });
};

/** Bulk upsert while a long build runs, so a crash halfway keeps what was done. */
export const POST: APIRoute = async ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const parsed = dossiersBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest(parsed.error.message);
  db.transaction((tx) => storeDossiers(tx as any, parsed.data));
  return Response.json({ dossiers: parsed.data.dossiers.length, notes: parsed.data.notes.length });
};
