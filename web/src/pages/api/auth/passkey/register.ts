import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { finishRegistration } from '../../../../lib/passkeys';

export const POST: APIRoute = async ({ locals, url, request }) => {
  if (!locals.owner) return new Response(null, { status: 401 });
  const body = await request.json().catch(() => null);
  if (!body?.challengeId || !body?.response) return Response.json({ ok: false, error: 'bad request' }, { status: 400 });
  const result = await finishRegistration(db, url, String(body.challengeId), body.response, String(body.name ?? ''));
  return Response.json(result, { status: result.ok ? 200 : 400, headers: { 'cache-control': 'no-store' } });
};
