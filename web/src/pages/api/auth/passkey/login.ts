import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { SESSION_COOKIE, SESSION_DAYS, createSession } from '../../../../lib/auth';
import { finishAuthentication } from '../../../../lib/passkeys';

/** The passkey ceremony's last step: a verified assertion becomes the same session cookie the password gives. */
export const POST: APIRoute = async ({ url, request, cookies }) => {
  const body = await request.json().catch(() => null);
  if (!body?.challengeId || !body?.response) return Response.json({ ok: false, error: 'bad request' }, { status: 400 });
  const result = await finishAuthentication(db, url, String(body.challengeId), body.response);
  if (!result.ok) return Response.json(result, { status: 401, headers: { 'cache-control': 'no-store' } });
  const s = createSession(db, request.headers.get('user-agent'));
  cookies.set(SESSION_COOKIE, s.id, { httpOnly: true, secure: url.protocol === 'https:', sameSite: 'lax', path: '/', maxAge: SESSION_DAYS * 86_400 });
  return Response.json({ ok: true, returnTo: '/tropes' }, { headers: { 'cache-control': 'no-store' } });
};
