import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { jobById, parseJson } from '../../../../lib/jobs/queue';
import { unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

/** Job status for the review page's poll (owner session) or the worker (bearer). */
export const GET: APIRoute = ({ request, params, locals }) => {
  if (!locals.owner && !workerAuthorized(db, request)) return unauthorized();
  const j = jobById(db, Number(params.id));
  if (!j) return Response.json({ error: 'no such job' }, { status: 404 });
  return Response.json({ id: j.id, kind: j.kind, status: j.status, progress: parseJson(j.progress, null), error: j.error, usage: parseJson(j.usage, null) });
};
