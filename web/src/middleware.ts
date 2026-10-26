import { defineMiddleware } from 'astro:middleware';
import { db } from './db';
import { SESSION_COOKIE, sessionIsValid } from './lib/auth';
import { LIMITS, bucketFor, clientAddress } from './lib/limits';

export const onRequest = defineMiddleware(async (context, next) => {
  context.locals.owner = sessionIsValid(db, context.cookies.get(SESSION_COOKIE)?.value);

  // Rate limits (plan Phase 6): searches, the read API and anonymous page views, per address.
  const bucket = bucketFor(context.url.pathname, context.locals.owner);
  if (bucket) {
    const verdict = LIMITS[bucket].take(clientAddress(context));
    if (!verdict.ok) {
      return new Response('Too many requests. Try again in a moment.\n', {
        status: 429,
        headers: { 'content-type': 'text/plain; charset=utf-8', 'retry-after': String(verdict.retryAfter), 'cache-control': 'no-store' },
      });
    }
  }

  const res = await next();
  // Cache headers: anonymous HTML may sit in a shared cache for a minute; the owner's pages never.
  const type = res.headers.get('content-type') ?? '';
  if (type.includes('text/html') && !res.headers.has('cache-control')) {
    res.headers.set('cache-control', context.locals.owner ? 'private, no-store' : 'public, max-age=60');
    res.headers.set('vary', 'Cookie');
  }
  return res;
});
