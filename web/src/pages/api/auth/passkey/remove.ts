import type { APIRoute } from 'astro';
import { eq } from 'drizzle-orm';
import { db } from '../../../../db';
import { passkey } from '../../../../db/schema';

/** A plain form post from the account page. */
export const POST: APIRoute = async ({ locals, request }) => {
  if (!locals.owner) return new Response(null, { status: 401 });
  const form = await request.formData().catch(() => null);
  const id = Number(form?.get('id'));
  if (Number.isInteger(id)) db.delete(passkey).where(eq(passkey.id, id)).run();
  return new Response(null, { status: 303, headers: { location: '/account' } });
};
