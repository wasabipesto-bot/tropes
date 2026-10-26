import type { APIContext } from 'astro';

/** A token bucket per key: `perMinute` tokens, refilled continuously. In memory, one process (plan Phase 6). */
export class Bucket {
  private tokens = new Map<string, { t: number; at: number }>();
  private takes = 0;
  constructor(public perMinute: number) {}

  take(key: string, now = Date.now()): { ok: true } | { ok: false; retryAfter: number } {
    const rate = this.perMinute / 60_000;
    const e = this.tokens.get(key) ?? { t: this.perMinute, at: now };
    e.t = Math.min(this.perMinute, e.t + (now - e.at) * rate);
    e.at = now;
    if (e.t >= 1) {
      e.t -= 1;
      this.tokens.set(key, e);
      this.prune(now);
      return { ok: true };
    }
    this.tokens.set(key, e);
    return { ok: false, retryAfter: Math.max(1, Math.ceil((1 - e.t) / rate / 1000)) };
  }

  private prune(now: number): void {
    if (++this.takes % 1000 !== 0) return;
    for (const [k, e] of this.tokens) if (now - e.at > 600_000) this.tokens.delete(k);
  }
}

export const LIMITS = {
  search: new Bucket(Number(process.env.TROPES_LIMIT_SEARCH ?? 30)),
  api: new Bucket(Number(process.env.TROPES_LIMIT_API ?? 60)),
  pages: new Bucket(Number(process.env.TROPES_LIMIT_PAGES ?? 120)),
};

/** The address a visitor is counted by. Behind Cloudflare or a reverse proxy, the forwarded header is trusted only when asked. */
export function clientAddress(ctx: Pick<APIContext, 'request' | 'clientAddress'>): string {
  if (process.env.TROPES_TRUSTED_PROXY === '1') {
    const cf = ctx.request.headers.get('cf-connecting-ip');
    if (cf) return cf.trim();
    const xff = ctx.request.headers.get('x-forwarded-for');
    if (xff) return xff.split(',').pop()!.trim();
  }
  try {
    return ctx.clientAddress;
  } catch {
    return 'unknown';
  }
}

const ASSETS = ['/_astro/', '/posters/', '/evidence/', '/sheets/', '/favicon', '/robots.txt'];
const WORKER = ['/api/jobs', '/api/export', '/api/sources', '/api/evidence', '/api/import', '/api/media', '/api/dossiers'];

/** Which bucket a request draws from; null for assets, the owner, and the workers' keyed routes. */
export function bucketFor(path: string, owner: boolean): keyof typeof LIMITS | null {
  if (ASSETS.some((p) => path.startsWith(p))) return null;
  if (path.startsWith('/api/v1')) return 'api';
  if (owner) return null;
  if (WORKER.some((p) => path.startsWith(p))) return null;
  if (path === '/search') return 'search';
  return 'pages';
}
