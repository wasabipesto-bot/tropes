import type { APIRoute } from 'astro';

/** Public pages are crawlable; the owner's and the workers' routes are not. */
export const GET: APIRoute = () =>
  new Response(
    ['User-agent: *', ...['/api/', '/review', '/metadata', '/update/', '/jobs', '/sheets/', '/evidence/pending/', '/login', '/account', '/recheck/', '/add/'].map((p) => `Disallow: ${p}`), ''].join('\n'),
    { headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'public, max-age=3600' } },
  );
