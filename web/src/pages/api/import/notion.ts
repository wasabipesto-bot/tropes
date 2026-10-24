import type { APIRoute } from 'astro';
import { db } from '../../../db';
import { afterNotionSync } from '../../../lib/jobs/auto';
import { notionImportBody } from '../../../lib/jobs/schemas';
import { importNotionRows } from '../../../lib/notion-import';
import { badRequest, unauthorized, workerAuthorized } from '../../../lib/worker-auth';

/** The worker's Notion sync hands every Media Log row here; the importer upserts and the automatic path queues follow-ups. */
export const POST: APIRoute = async ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const parsed = notionImportBody.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest(parsed.error.message);
  const report = importNotionRows(db, parsed.data.rows, { complete: parsed.data.complete });
  const queued = afterNotionSync(db, report);
  return Response.json({ ...report, queued });
};
