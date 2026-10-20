import { createHash, randomBytes } from 'node:crypto';
import { eq, sql } from 'drizzle-orm';
import type { Db } from '../db/open';
import { apiKey } from '../db/schema';

export function hashToken(token: string): string {
  return createHash('sha256').update(token).digest('hex');
}

/** Create a worker token. The plain token is returned once and never stored. */
export function createApiKey(db: Db, name: string): string {
  const token = 'tl_' + randomBytes(24).toString('base64url');
  db.insert(apiKey).values({ name, hash: hashToken(token) }).run();
  return token;
}

/** True when the request carries a valid worker bearer token. Touches last_used_at. */
export function workerAuthorized(db: Db, request: Request): boolean {
  const auth = request.headers.get('authorization') ?? '';
  const m = /^Bearer\s+(\S+)$/i.exec(auth);
  if (!m) return false;
  const row = db.select().from(apiKey).where(eq(apiKey.hash, hashToken(m[1]))).get();
  if (!row) return false;
  db.update(apiKey).set({ lastUsedAt: sql`(datetime('now'))` }).where(eq(apiKey.id, row.id)).run();
  return true;
}

export const unauthorized = () => Response.json({ error: 'unauthorized' }, { status: 401 });
export const badRequest = (message: string) => Response.json({ error: message }, { status: 400 });
