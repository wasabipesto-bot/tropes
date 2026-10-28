import { and, asc, desc, eq, inArray, isNull, or, sql } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { dossier, instance, job, media, mediaNote, proposal, type Job } from '../../db/schema';
import type { z } from 'astro/zod';
import type { dossiersBody } from './schemas';
import { payloadByKind, type JobKind, type ResultBody } from './schemas';
import { discardPendingEvidence } from './commit';

export const STALE_MINUTES = 10;
export const MAX_ATTEMPTS = 2;

export function createJob(db: Db, kind: JobKind, payload: unknown): Job {
  const parsed = payloadByKind[kind].parse(payload);
  return db.insert(job).values({ kind, payload: JSON.stringify(parsed) }).returning().get();
}

/** Running jobs whose worker went quiet go back to the queue once, then fail. Loud, not silent. */
export function reclaimStale(db: Db): void {
  const cutoff = sql`datetime('now', ${`-${STALE_MINUTES} minutes`})`;
  db.update(job)
    .set({ status: 'failed', error: 'worker stopped responding', finishedAt: sql`(datetime('now'))` })
    .where(and(eq(job.status, 'running'), sql`${job.heartbeatAt} < ${cutoff}`, sql`${job.attempts} >= ${MAX_ATTEMPTS}`))
    .run();
  db.update(job)
    .set({ status: 'queued', claimedAt: null, heartbeatAt: null })
    .where(and(eq(job.status, 'running'), sql`${job.heartbeatAt} < ${cutoff}`))
    .run();
}

/** Atomically take the oldest queued job of the given kinds. */
export function claimJob(db: Db, kinds: JobKind[]): Job | undefined {
  reclaimStale(db);
  if (kinds.length === 0) return undefined;
  return db.transaction((tx) => {
    // Short jobs first: frames for a review page should not wait behind a day of contact sheets or Whisper.
    const rank = sql`case ${job.kind} when 'extract_evidence' then 0 when 'look_frames' then 0 when 'find_evidence' then 0 when 'ping' then 0 when 'make_sheets' then 2 when 'transcribe' then 2 else 1 end`;
    const next = tx.select({ id: job.id }).from(job).where(and(eq(job.status, 'queued'), inArray(job.kind, kinds))).orderBy(rank, asc(job.id)).get();
    if (!next) return undefined;
    return tx
      .update(job)
      .set({ status: 'running', claimedAt: sql`(datetime('now'))`, heartbeatAt: sql`(datetime('now'))`, attempts: sql`${job.attempts} + 1` })
      .where(and(eq(job.id, next.id), eq(job.status, 'queued')))
      .returning()
      .get();
  });
}

export function progressJob(db: Db, id: number, progress: { done: number; total: number; note?: string }): Job | undefined {
  db.update(job).set({ progress: JSON.stringify(progress), heartbeatAt: sql`(datetime('now'))` }).where(and(eq(job.id, id), eq(job.status, 'running'))).run();
  return db.select().from(job).where(eq(job.id, id)).get();
}

export function failJob(db: Db, id: number, error: string): void {
  db.update(job).set({ status: 'failed', error, finishedAt: sql`(datetime('now'))` }).where(eq(job.id, id)).run();
}

export function cancelJob(db: Db, id: number): void {
  db.transaction((tx) => {
    for (const p of tx.select({ id: proposal.id }).from(proposal).where(eq(proposal.jobId, id)).all()) discardPendingEvidence(p.id);
    tx.delete(proposal).where(eq(proposal.jobId, id)).run();
    tx.update(job).set({ status: 'cancelled', finishedAt: sql`(datetime('now'))` }).where(eq(job.id, id)).run();
  });
}

/** Upsert dossiers and replace notes per work and source. Used by job results and the bulk endpoint. */
export function storeDossiers(tx: Db, body: z.infer<typeof dossiersBody>): void {
  for (const d of body.dossiers) {
    tx.insert(dossier)
      .values({ subjectKind: d.subject.kind, subjectId: d.subject.id, depth: d.depth, body: JSON.stringify(d.body), model: d.model, promptVersion: d.promptVersion, sourceHash: d.sourceHash ?? null, inputs: JSON.stringify(d.inputs ?? {}) })
      .onConflictDoUpdate({
        target: [dossier.subjectKind, dossier.subjectId],
        set: { depth: d.depth, body: JSON.stringify(d.body), model: d.model, promptVersion: d.promptVersion, sourceHash: d.sourceHash ?? null, inputs: JSON.stringify(d.inputs ?? {}), builtAt: sql`(datetime('now'))` },
      })
      .run();
  }
  // Notes replace per work, source and label, so one episode's visual notes never wipe another's.
  const cleared = new Set<string>();
  for (const n of body.notes) {
    const label = n.label ?? '';
    const key = `${n.mediaId}:${n.source}:${label}`;
    if (!cleared.has(key)) {
      tx.delete(mediaNote).where(and(eq(mediaNote.mediaId, n.mediaId), eq(mediaNote.source, n.source), eq(mediaNote.label, label))).run();
      cleared.add(key);
    }
    tx.insert(mediaNote).values({ mediaId: n.mediaId, source: n.source, url: n.url ?? null, text: n.text, label }).run();
  }
}

/** Store everything a finished job produced, in one transaction. */
export function completeJob(db: Db, id: number, body: ResultBody): void {
  db.transaction((tx) => {
    tx.delete(proposal).where(eq(proposal.jobId, id)).run();
    for (const p of body.proposals) {
      tx.insert(proposal)
        .values({
          jobId: id,
          tropeId: p.tropeId ?? null,
          subjectKind: p.subject.kind,
          subjectId: p.subject.id,
          kind: p.kind,
          targetInstanceId: p.targetInstanceId ?? null,
          score: p.score,
          prominence: p.prominence,
          who: p.who,
          text: p.text,
          evidence: JSON.stringify(p.evidence),
          seed: p.seed,
          rejectedBefore: p.rejectedBefore,
          flags: JSON.stringify(p.flags),
          payload: JSON.stringify(p.payload ?? {}),
        })
        .run();
    }
    storeDossiers(tx as unknown as Db, { dossiers: body.dossiers, notes: body.notes });
    // A look at the frames (plan D12): a flag either way, and a lower score when nothing in the pictures showed the trope.
    for (const v of body.verdicts ?? []) {
      const p = tx.select().from(proposal).where(eq(proposal.id, v.proposalId)).get();
      if (!p) continue;
      const flags = parseJson<string[]>(p.flags, []).filter((f) => !f.startsWith('screenshots: '));
      flags.push(v.seen ? `screenshots: ${v.note || 'the trope is visible'}` : `screenshots: not seen${v.note ? ` (${v.note})` : ''}`);
      const pl = parseJson<any>(p.payload, {});
      pl.look = { seen: v.seen, note: v.note };
      tx.update(proposal).set({ flags: JSON.stringify(flags), payload: JSON.stringify(pl), score: v.seen ? p.score : Math.round(p.score * 50) / 100 }).where(eq(proposal.id, p.id)).run();
    }
    // Entry texts written for instances that had none (write_instances): stored, unverified, for the owner to read.
    for (const r of body.rewrites ?? []) {
      tx.update(instance).set({ who: r.who, text: r.text, verified: false, updatedAt: sql`(datetime('now'))`, ...(r.prominence ? { prominence: r.prominence } : {}) }).where(eq(instance.id, r.instanceId)).run();
    }
    // Model-written description drafts never replace the owner's words.
    for (const d of body.descriptions ?? []) {
      tx.update(media)
        .set({ description: d.text, descriptionOrigin: 'model', updatedAt: sql`(datetime('now'))` })
        .where(and(eq(media.id, d.mediaId), or(isNull(media.description), eq(media.descriptionOrigin, 'model'))))
        .run();
    }
    tx.update(job)
      .set({ status: 'done', result: JSON.stringify({ summary: body.summary, warnings: body.warnings }), usage: JSON.stringify(body.usage ?? {}), finishedAt: sql`(datetime('now'))`, progress: null })
      .where(eq(job.id, id))
      .run();
  });
}

export function latestJob(db: Db, kind: JobKind, match: (payload: any) => boolean): Job | undefined {
  return db.select().from(job).where(eq(job.kind, kind)).orderBy(desc(job.id)).all().find((j) => match(JSON.parse(j.payload)));
}

export function jobById(db: Db, id: number): Job | undefined {
  return db.select().from(job).where(eq(job.id, id)).get();
}

export function parseJson<T = unknown>(s: string | null, fallback: T): T {
  if (!s) return fallback;
  try { return JSON.parse(s) as T; } catch { return fallback; }
}
