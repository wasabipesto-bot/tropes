import type { APIRoute } from 'astro';
import { count } from 'drizzle-orm';
import { db } from '../../db';
import { media } from '../../db/schema';
import pkg from '../../../package.json';

export const GET: APIRoute = () => {
  const [{ n }] = db.select({ n: count() }).from(media).all();
  return Response.json({ ok: true, media: n, version: pkg.version });
};
