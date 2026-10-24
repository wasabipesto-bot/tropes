import type { APIRoute } from 'astro';
import { db } from '../../../db';
import { createJob } from '../../../lib/jobs/queue';
import { createJobBody } from '../../../lib/jobs/schemas';
import { badRequest, unauthorized, workerAuthorized } from '../../../lib/worker-auth';

/** Queue a job from the worker (its Notion sync timer). Owner-started jobs go through Actions instead. */
export const POST: APIRoute = async ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const parsed = createJobBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest(parsed.error.message);
  try {
    const j = createJob(db, parsed.data.kind, parsed.data.payload);
    return Response.json({ id: j.id, kind: j.kind, status: j.status });
  } catch (e) {
    return badRequest(e instanceof Error ? e.message : String(e));
  }
};
