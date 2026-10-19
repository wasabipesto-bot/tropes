import { defineMiddleware } from 'astro:middleware';
import { db } from './db';
import { SESSION_COOKIE, sessionIsValid } from './lib/auth';

export const onRequest = defineMiddleware((context, next) => {
  context.locals.owner = sessionIsValid(db, context.cookies.get(SESSION_COOKIE)?.value);
  return next();
});
