import type { APIRoute } from 'astro';
import { db } from '../../../db';
import { genreVocabulary } from '../../../lib/genres';
import { unauthorized, workerAuthorized } from '../../../lib/worker-auth';

/** The controlled genre vocabulary (web/seed/genres.json) for the worker's genre-mapping prompt. */
export const GET: APIRoute = ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  return Response.json(genreVocabulary());
};
