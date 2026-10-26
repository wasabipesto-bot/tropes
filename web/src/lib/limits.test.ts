import { describe, expect, it } from 'vitest';
import { Bucket, bucketFor, clientAddress } from './limits';

describe('rate limits', () => {
  it('a bucket allows its per-minute count at once, then refills continuously', () => {
    const b = new Bucket(6);
    const t0 = 1_000_000;
    for (let i = 0; i < 6; i++) expect(b.take('a', t0).ok).toBe(true);
    const denied = b.take('a', t0);
    expect(denied.ok).toBe(false);
    expect(!denied.ok && denied.retryAfter).toBe(10);
    expect(b.take('a', t0 + 10_000).ok).toBe(true);
    expect(b.take('b', t0).ok).toBe(true);
  });

  it('routes requests to the right bucket and exempts assets, the owner and the workers', () => {
    expect(bucketFor('/search', false)).toBe('search');
    expect(bucketFor('/api/v1/tropes', false)).toBe('api');
    expect(bucketFor('/api/v1/tropes', true)).toBe('api');
    expect(bucketFor('/tropes/x', false)).toBe('pages');
    expect(bucketFor('/tropes/x', true)).toBeNull();
    expect(bucketFor('/posters/1-300.webp', false)).toBeNull();
    expect(bucketFor('/api/jobs/claim', false)).toBeNull();
  });

  it('trusts forwarded addresses only when told to', () => {
    const req = new Request('http://x/', { headers: { 'cf-connecting-ip': '9.9.9.9', 'x-forwarded-for': '1.1.1.1, 2.2.2.2' } });
    delete process.env.TROPES_TRUSTED_PROXY;
    expect(clientAddress({ request: req, clientAddress: '10.0.0.1' })).toBe('10.0.0.1');
    process.env.TROPES_TRUSTED_PROXY = '1';
    expect(clientAddress({ request: req, clientAddress: '10.0.0.1' })).toBe('9.9.9.9');
    const req2 = new Request('http://x/', { headers: { 'x-forwarded-for': '1.1.1.1, 2.2.2.2' } });
    expect(clientAddress({ request: req2, clientAddress: '10.0.0.1' })).toBe('2.2.2.2');
    delete process.env.TROPES_TRUSTED_PROXY;
  });
});
