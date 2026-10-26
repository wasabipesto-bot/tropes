import { and, desc, eq, sql } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { job, proposal, type Job } from '../../db/schema';
import { parseJson } from './queue';

export interface PendingReview { job: Job; kind: Job['kind']; createdAt: string; href: string; pending: number }

/** Finished jobs that still hold undecided proposals, newest first, with the page that reviews each (plan T12). */
export function pendingReviews(db: Db): PendingReview[] {
  const rows = db
    .select({ j: job, n: sql<number>`count(*)` })
    .from(job)
    .innerJoin(proposal, and(eq(proposal.jobId, job.id), eq(proposal.decision, 'pending')))
    .where(eq(job.status, 'done'))
    .groupBy(job.id)
    .orderBy(desc(job.id))
    .all();
  return rows.map(({ j, n }) => ({ job: j, kind: j.kind, createdAt: j.createdAt, href: reviewHref(db, j), pending: n }));
}

/** Where a job's proposals are reviewed. */
export function reviewHref(db: Db, j: Job): string {
  const payload = parseJson<any>(j.payload, {});
  if (j.kind === 'scan_trope') {
    if (payload.tropeId) {
      const slug = db.$client.prepare('select slug from trope where id = ?').pluck().get(payload.tropeId) as string | undefined;
      return slug ? `/recheck/trope/${slug}?job=${j.id}` : `/jobs?job=${j.id}`;
    }
    return `/add/trope?job=${j.id}`;
  }
  if (j.kind === 'check_subject') {
    const s = payload.subject ?? {};
    return s.kind === 'media' ? `/update/media/${s.id}?job=${j.id}` : `/recheck/series/${s.id}?job=${j.id}`;
  }
  if (j.kind === 'lookup_media') return `/metadata?job=${j.id}`;
  return `/jobs?job=${j.id}`;
}

/** The newest finished job for one subject or trope that still has undecided proposals. */
export function pendingReviewFor(db: Db, kind: 'media' | 'series' | 'trope', id: number): PendingReview | null {
  for (const r of pendingReviews(db)) {
    const payload = parseJson<any>(r.job.payload, {});
    if (kind === 'trope' && r.kind === 'scan_trope' && payload.tropeId === id) return r;
    if (kind !== 'trope' && r.kind === 'check_subject' && payload.subject?.kind === kind && payload.subject?.id === id) return r;
  }
  return null;
}

/** The newest find_evidence job for an instance, for the edit panel's status line. */
export function evidenceSearchFor(db: Db, instanceId: number): Job | undefined {
  return db.select().from(job).where(eq(job.kind, 'find_evidence')).orderBy(desc(job.id)).limit(50).all().find((j) => parseJson<any>(j.payload, {}).instanceId === instanceId);
}
