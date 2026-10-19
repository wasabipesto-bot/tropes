import { randomBytes } from 'node:crypto';
import { eq, lt } from 'drizzle-orm';
import type { Db } from '../db/open';
import { session } from '../db/schema';

export const SESSION_COOKIE = 'tl_session';
export const SESSION_DAYS = 90;

function isoIn(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString();
}

export function createSession(db: Db, userAgent: string | null): { id: string; expiresAt: string } {
  const id = randomBytes(32).toString('base64url');
  const expiresAt = isoIn(SESSION_DAYS);
  db.insert(session).values({ id, expiresAt, userAgent }).run();
  db.delete(session).where(lt(session.expiresAt, new Date().toISOString())).run();
  return { id, expiresAt };
}

/** True when the id names a live session. Expired rows are removed on sight. */
export function sessionIsValid(db: Db, id: string | undefined): boolean {
  if (!id) return false;
  const row = db.select().from(session).where(eq(session.id, id)).get();
  if (!row) return false;
  if (row.expiresAt <= new Date().toISOString()) {
    db.delete(session).where(eq(session.id, id)).run();
    return false;
  }
  return true;
}

export function deleteSession(db: Db, id: string | undefined): void {
  if (id) db.delete(session).where(eq(session.id, id)).run();
}

/** Tiny in-memory limiter for the login form: `max` attempts per `windowMs` per key. */
export class RateLimiter {
  private hits = new Map<string, { count: number; resetAt: number }>();
  constructor(private max = 5, private windowMs = 60_000) {}
  allow(key: string, now = Date.now()): boolean {
    const h = this.hits.get(key);
    if (!h || h.resetAt <= now) {
      this.hits.set(key, { count: 1, resetAt: now + this.windowMs });
      return true;
    }
    h.count++;
    return h.count <= this.max;
  }
}
