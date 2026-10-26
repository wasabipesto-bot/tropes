import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { registrationOptions } from '../../../../lib/passkeys';

export const POST: APIRoute = async ({ locals, url }) => {
  if (!locals.owner) return new Response(null, { status: 401 });
  return Response.json(await registrationOptions(db, url), { headers: { 'cache-control': 'no-store' } });
};
