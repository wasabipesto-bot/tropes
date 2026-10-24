import { eq } from 'drizzle-orm';
import { describe, expect, it } from 'vitest';
import { openDb } from '../../db/open';
import { evidence, instance, job, media, proposal, trope } from '../../db/schema';
import { commitProposals } from './commit';
import { exportTropes } from './export';
import { claimJob, completeJob, createJob, failJob, progressJob, reclaimStale } from './queue';
import { calibrationLine, proposalsFor } from './view';
import { createApiKey, hashToken, workerAuthorized } from '../worker-auth';

function seed() {
  const db = openDb(':memory:');
  const m1 = db.insert(media).values({ title: 'Pantheon', type: 'TV Series' }).returning().get();
  const m2 = db.insert(media).values({ title: 'SPY x FAMILY', type: 'TV Series' }).returning().get();
  return { db, m1, m2 };
}

describe('job queue', () => {
  it('creates, claims atomically, progresses and completes', () => {
    const { db, m1 } = seed();
    const j = createJob(db, 'scan_trope', { mode: 'add', draft: { name: 'Dog Duo', description: 'd', seeds: ['Pantheon'] } });
    expect(j.status).toBe('queued');
    expect(claimJob(db, ['ping'])).toBeUndefined();
    const c = claimJob(db, ['scan_trope'])!;
    expect(c.id).toBe(j.id);
    expect(c.status).toBe('running');
    expect(claimJob(db, ['scan_trope'])).toBeUndefined();
    expect(progressJob(db, j.id, { done: 1, total: 2 })?.progress).toContain('"done":1');
    completeJob(db, j.id, {
      summary: { proposals: 1, seeds: [{ title: 'Pantheon', resolved: true, found: true, score: 0.9 }] },
      proposals: [{ tropeId: null, subject: { kind: 'media', id: m1.id }, kind: 'instance', score: 0.9, prominence: 'core', who: 'UIs', text: 'Text.', evidence: [{ kind: 'quote', content: 'q', locator: 'ch. 1' }], seed: true, rejectedBefore: false, flags: [], payload: {} }],
      dossiers: [{ subject: { kind: 'media', id: m1.id }, depth: 'knowledge', body: { known: 'strong' }, model: 'm', promptVersion: 1 }],
      notes: [{ mediaId: m1.id, source: 'tumblr', url: null, text: 'a post' }],
      usage: { calls: 3, promptTokens: 10, completionTokens: 5, cachedTokens: 0, costUsd: 0.01 },
      descriptions: [], warnings: [],
    });
    const done = db.select().from(job).where(eq(job.id, j.id)).get()!;
    expect(done.status).toBe('done');
    expect(JSON.parse(done.usage!).calls).toBe(3);
    const views = proposalsFor(db, done, 0.5);
    expect(views).toHaveLength(1);
    expect(views[0].checked).toBe(true);
    expect(calibrationLine(JSON.parse(done.result!).summary, 0.5)).toBe('Found your example, scoring 0.90. Anything under 0.5 starts unchecked.');
  });

  it('reclaims a stale running job once, then fails it', () => {
    const { db } = seed();
    const j = createJob(db, 'ping', {});
    claimJob(db, ['ping']);
    db.update(job).set({ heartbeatAt: '2000-01-01 00:00:00' }).where(eq(job.id, j.id)).run();
    reclaimStale(db);
    expect(db.select().from(job).where(eq(job.id, j.id)).get()!.status).toBe('queued');
    claimJob(db, ['ping']);
    db.update(job).set({ heartbeatAt: '2000-01-01 00:00:00' }).where(eq(job.id, j.id)).run();
    reclaimStale(db);
    const after = db.select().from(job).where(eq(job.id, j.id)).get()!;
    expect(after.status).toBe('failed');
    expect(after.error).toContain('stopped responding');
    failJob(db, j.id, 'boom');
    expect(db.select().from(job).where(eq(job.id, j.id)).get()!.error).toBe('boom');
  });

  it('commits accepted proposals into a new trope, remembers rejections, and ranks them last next time', () => {
    const { db, m1, m2 } = seed();
    const j = createJob(db, 'scan_trope', { mode: 'add', draft: { name: 'Dog Duo', description: 'd', seeds: [] } });
    claimJob(db, ['scan_trope']);
    completeJob(db, j.id, {
      summary: {},
      proposals: [
        { subject: { kind: 'media', id: m1.id }, kind: 'instance', score: 0.9, prominence: 'core', who: 'A', text: 'One.', evidence: [{ kind: 'quote', content: 'q1', locator: '' }], seed: false, rejectedBefore: false, flags: [], payload: {} },
        { subject: { kind: 'media', id: m2.id }, kind: 'instance', score: 0.6, prominence: 'brief', who: 'B', text: 'Two.', evidence: [], seed: false, rejectedBefore: false, flags: [], payload: {} },
      ],
      dossiers: [], notes: [], descriptions: [], warnings: [],
    });
    const ids = db.select().from(proposal).all().map((p) => p.id);
    const out = commitProposals(db, j.id, new Set([ids[0]]), { [String(ids[0])]: 'recurring' });
    expect(out.created).toBe(1);
    expect(out.returnTo).toBe('/tropes/dog-duo?added=1');
    const t = db.select().from(trope).where(eq(trope.slug, 'dog-duo')).get()!;
    const inst = db.select().from(instance).all();
    expect(inst).toHaveLength(1);
    expect(inst[0].prominence).toBe('recurring');
    expect(inst[0].origin).toBe('model');
    expect(inst[0].verified).toBe(true); // the owner reviewed it (plan T16)
    expect(db.select().from(evidence).all()).toHaveLength(1);
    const exported = exportTropes(db).find((x) => x.id === t.id)!;
    expect(exported.rejected).toEqual([{ kind: 'media', id: m2.id }]);
    expect(exported.instances[0].verified).toBe(true);
    // A second commit of the same job does nothing destructive.
    expect(() => commitProposals(db, j.id, new Set(ids), {})).not.toThrow();
    expect(db.select().from(instance).all()).toHaveLength(2);
  });

  it('commits the automatic path unverified and leaves the rest pending for review', () => {
    const { db, m1, m2 } = seed();
    const t = db.insert(trope).values({ name: 'Dog Duo', slug: 'dog-duo', description: 'd' }).returning().get();
    const j = createJob(db, 'check_subject', { mode: 'add', subject: { kind: 'media', id: m1.id }, auto: true });
    claimJob(db, ['check_subject']);
    completeJob(db, j.id, {
      summary: {},
      proposals: [
        { tropeId: t.id, subject: { kind: 'media', id: m1.id }, kind: 'instance', score: 0.9, prominence: 'core', who: '', text: 'One.', evidence: [], seed: false, rejectedBefore: false, flags: [], payload: {} },
        { tropeId: t.id, subject: { kind: 'media', id: m2.id }, kind: 'instance', score: 0.55, prominence: 'brief', who: '', text: 'Two.', evidence: [], seed: false, rejectedBefore: false, flags: [], payload: {} },
      ],
      dossiers: [], notes: [], descriptions: [], warnings: [],
    });
    const ids = db.select().from(proposal).all();
    commitProposals(db, j.id, new Set([ids[0].id]), {}, { verified: false, rejectRest: false });
    const inst = db.select().from(instance).all();
    expect(inst).toHaveLength(1);
    expect(inst[0].verified).toBe(false);
    expect(inst[0].origin).toBe('auto');
    const decisions = db.select().from(proposal).all().map((p) => p.decision);
    expect(decisions).toEqual(['accepted', 'pending']);
  });

  it('authorizes workers by hashed bearer token', () => {
    const { db } = seed();
    const token = createApiKey(db, 'test');
    expect(hashToken(token)).not.toBe(token);
    expect(workerAuthorized(db, new Request('http://x/', { headers: { authorization: `Bearer ${token}` } }))).toBe(true);
    expect(workerAuthorized(db, new Request('http://x/', { headers: { authorization: 'Bearer nope' } }))).toBe(false);
    expect(workerAuthorized(db, new Request('http://x/'))).toBe(false);
  });
});
