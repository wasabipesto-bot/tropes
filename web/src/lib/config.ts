/** The public origin (https://tropes.wasabipesto.com): absolute links for OG tags and canonicals, the passkey rpID. */
export const SITE_ORIGIN = (process.env.SITE_ORIGIN ?? '').replace(/\/+$/, '');

export function absolute(path: string, fallbackOrigin?: string): string {
  const origin = SITE_ORIGIN || fallbackOrigin || '';
  return origin ? `${origin}${path}` : path;
}

/** The hostname passkeys are bound to: the public one when configured, else the request's (dev, tests). */
export function rpIdFor(requestUrl: URL): string {
  return SITE_ORIGIN ? new URL(SITE_ORIGIN).hostname : requestUrl.hostname;
}

export function originFor(requestUrl: URL): string {
  return SITE_ORIGIN || requestUrl.origin;
}
