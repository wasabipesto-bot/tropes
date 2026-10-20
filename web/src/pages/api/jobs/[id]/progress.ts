import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { progressBody } from '../../../../lib/jobs/schemas';
import { progressJob } from '../../../../lib/jobs/queue';
import { badRequest, unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

export const POST: APIRoute = async ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const parsed = progressBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest(parsed.error.message);
  const j = progressJob(db, Number(params.id), parsed.data);
  if (!j) return Response.json({ error: 'no such job' }, { status: 404 });
  return Response.json({ status: j.status });
};
