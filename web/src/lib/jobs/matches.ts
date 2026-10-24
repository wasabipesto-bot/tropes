import { and, asc, desc, eq, inArray, isNull, or, sql } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { job, media, proposal, type Job, type Media, type Proposal } from '../../db/schema';
import type { Candidate, MatchPayload } from '../metadata';
import { parseJson } from './queue';

export interface MatchView {
  p: Proposal;
  m: Media;
  payload: MatchPayload;
}

/** A lookup job's match proposals with their media rows, in title order. */
export function matchesFor(db: Db, j: Job): MatchView[] {
  const rows = db.select().from(proposal).where(and(eq(proposal.jobId, j.id), eq(proposal.kind, 'match'))).orderBy(asc(proposal.id)).all();
  if (rows.length === 0) return [];
  const mediaRows = db.select().from(media).where(inArray(media.id, rows.map((r) => r.subjectId))).all();
  const out: MatchView[] = [];
  for (const p of rows) {
    const m = mediaRows.find((x) => x.id === p.subjectId);
    const payload = parseJson<MatchPayload | null>(p.payload, null);
    if (m && payload) out.push({ p, m, payload });
  }
  return out.sort((a, b) => a.m.title.localeCompare(b.m.title));
}

/** Entries a backfill should look up: never looked up, or not found last time. */
export function unresolvedMediaIds(db: Db): number[] {
  return db.select({ id: media.id }).from(media).where(or(isNull(media.identity), eq(media.identity, 'not_found'))).all().map((r) => r.id);
}

export function pinnedMediaIds(db: Db): number[] {
  return db.select({ id: media.id }).from(media).where(eq(media.identity, 'pinned')).all().map((r) => r.id);
}

export function identityCounts(db: Db): Record<string, number> {
  const rows = db.select({ identity: media.identity, n: sql<number>`count(*)` }).from(media).groupBy(media.identity).all();
  const out: Record<string, number> = { pinned: 0, check: 0, not_found: 0, none: 0, never: 0 };
  for (const r of rows) out[r.identity ?? 'never'] = r.n;
  return out;
}

/** Finished lookup jobs that still have undecided matches, newest first, with the count waiting in each. */
export function pendingLookupJobs(db: Db): { job: Job; pending: number }[] {
  const jobs = db.select().from(job).where(and(eq(job.kind, 'lookup_media'), eq(job.status, 'done'))).orderBy(desc(job.id)).limit(40).all();
  const out: { job: Job; pending: number }[] = [];
  for (const j of jobs) {
    const [{ n }] = db.select({ n: sql<number>`count(*)` }).from(proposal).where(and(eq(proposal.jobId, j.id), eq(proposal.decision, 'pending'))).all();
    if (n > 0) out.push({ job: j, pending: n });
  }
  return out;
}

/** The backfill runs in batches so a failed job loses at most one batch; each batch is reviewed on its own. */
export const BACKFILL_BATCH = 200;

/** "Pantheon (Q109639866): animated television series, 2022, Netflix" for a candidate line. */
export function candidateLine(c: Candidate): string {
  const parts = [c.description || c.kinds.join(', ')];
  if (c.year) parts.push(String(c.year));
  if (c.creator) parts.push(c.creator);
  return parts.filter(Boolean).join(' · ');
}
