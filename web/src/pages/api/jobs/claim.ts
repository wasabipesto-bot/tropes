import type { APIRoute } from 'astro';
import { db } from '../../../db';
import { JOB_KINDS } from '../../../db/schema';
import { claimJob } from '../../../lib/jobs/queue';
import { unauthorized, workerAuthorized } from '../../../lib/worker-auth';

export const POST: APIRoute = async ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const body = await request.json().catch(() => ({}));
  const kinds = Array.isArray(body?.kinds) ? body.kinds.filter((k: string) => (JOB_KINDS as readonly string[]).includes(k)) : [...JOB_KINDS];
  const j = claimJob(db, kinds);
  if (!j) return new Response(null, { status: 204 });
  return Response.json({ id: j.id, kind: j.kind, payload: JSON.parse(j.payload), attempts: j.attempts });
};
