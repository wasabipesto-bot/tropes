import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { failJob, jobById } from '../../../../lib/jobs/queue';
import { unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

export const POST: APIRoute = async ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const id = Number(params.id);
  if (!jobById(db, id)) return Response.json({ error: 'no such job' }, { status: 404 });
  const body = await request.json().catch(() => ({}));
  failJob(db, id, String(body?.error ?? 'failed'));
  return Response.json({ status: 'failed' });
};
