import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { authenticationOptions } from '../../../../lib/passkeys';

export const POST: APIRoute = async ({ url }) => Response.json(await authenticationOptions(db, url), { headers: { 'cache-control': 'no-store' } });
