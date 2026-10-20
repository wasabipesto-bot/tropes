import type { APIRoute } from 'astro';
import { and, eq } from 'drizzle-orm';
import { db } from '../../../../db';
import { dossier } from '../../../../db/schema';
import { unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

export const GET: APIRoute = ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const kind = params.kind === 'series' ? 'series' : 'media';
  const d = db.select().from(dossier).where(and(eq(dossier.subjectKind, kind), eq(dossier.subjectId, Number(params.id)))).get();
  if (!d) return Response.json({ error: 'no dossier' }, { status: 404 });
  return Response.json({ ...d, body: JSON.parse(d.body) });
};
