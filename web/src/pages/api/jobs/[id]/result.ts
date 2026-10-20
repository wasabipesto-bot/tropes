import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { resultBody } from '../../../../lib/jobs/schemas';
import { completeJob, jobById } from '../../../../lib/jobs/queue';
import { badRequest, unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

export const POST: APIRoute = async ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const id = Number(params.id);
  const j = jobById(db, id);
  if (!j) return Response.json({ error: 'no such job' }, { status: 404 });
  if (j.status !== 'running') return Response.json({ error: `job is ${j.status}` }, { status: 409 });
  const parsed = resultBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest(parsed.error.message);
  completeJob(db, id, parsed.data);
  return Response.json({ status: 'done', proposals: parsed.data.proposals.length, dossiers: parsed.data.dossiers.length });
};
