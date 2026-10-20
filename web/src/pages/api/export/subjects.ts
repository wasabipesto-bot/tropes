import type { APIRoute } from 'astro';
import { db } from '../../../db';
import { exportSubjects } from '../../../lib/jobs/export';
import { unauthorized, workerAuthorized } from '../../../lib/worker-auth';

export const GET: APIRoute = ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  return Response.json(exportSubjects(db));
};
