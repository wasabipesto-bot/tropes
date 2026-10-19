import { defineMiddleware } from 'astro:middleware';

// Phase 2 replaces this with session-cookie resolution. Until then every
// request is anonymous, so the owner controls never render.
export const onRequest = defineMiddleware((context, next) => {
  context.locals.owner = false;
  return next();
});
