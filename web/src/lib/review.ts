import { and, desc, eq, gte, inArray, isNotNull, sql } from 'drizzle-orm';
import type { Db } from '../db/open';
import { instance, job, media, proposal, trope, type Media } from '../db/schema';
import { parseJson } from './jobs/queue';
import { pendingReviews, type PendingReview } from './jobs/pending';

/** Everything waiting on the owner (plan T12): a plain list of links to pages that already exist. */
export interface ReviewItems {
  jobs: PendingReview[];
  /** Entries whose match needs checking and are not already covered by a pending lookup proposal. */
  identity: Media[];
  /** Entries gone from Notion. */
  missing: Media[];
  /** Entries the sync flagged (a changed Media Link on a pinned match). */
  flagged: Media[];
  /** Instances the automatic path added recently, still unverified. */
  auto: { id: number; createdAt: string; tropeName: string; tropeSlug: string; subjectId: number; title: string }[];
  /** From the latest full index of the media disk: works whose folder needs a look, and works not on the disk (plan T2). */
  files: { checks: { mediaId: number | null; title: string; why: string; folders: string[] }[]; missing: string[]; at: string | null };
}

export const AUTO_WINDOW_DAYS = 14;

export function reviewItems(db: Db): ReviewItems {
  const jobs = pendingReviews(db);
  const covered = new Set(
    db.select({ id: proposal.subjectId }).from(proposal).where(and(eq(proposal.kind, 'match'), eq(proposal.decision, 'pending'))).all().map((r) => r.id),
  );
  const identity = db.select().from(media).where(eq(media.identity, 'check')).all().filter((m) => !covered.has(m.id));
  const missing = db.select().from(media).where(isNotNull(media.notionMissingSince)).all();
  const flagged = db.select().from(media).where(isNotNull(media.reviewNote)).all();
  const since = sql`datetime('now', ${`-${AUTO_WINDOW_DAYS} days`})`;
  const rows = db
    .select({ id: instance.id, createdAt: instance.createdAt, tropeName: trope.name, tropeSlug: trope.slug, subjectId: instance.subjectId, subjectKind: instance.subjectKind })
    .from(instance)
    .innerJoin(trope, eq(trope.id, instance.tropeId))
    .where(and(eq(instance.origin, 'auto'), eq(instance.verified, false), gte(instance.createdAt, since)))
    .orderBy(desc(instance.id))
    .all();
  const titles = new Map(rows.length ? db.select({ id: media.id, title: media.title }).from(media).where(inArray(media.id, rows.map((r) => r.subjectId))).all().map((r) => [r.id, r.title]) : []);
  const auto = rows.filter((r) => r.subjectKind === 'media').map((r) => ({ ...r, title: titles.get(r.subjectId) ?? '' }));
  // The last index of the whole disk (a per-work refresh only knows about its work); pinned works drop out of the lists.
  const index = db.select().from(job).where(and(eq(job.kind, 'index_local'), eq(job.status, 'done'))).orderBy(desc(job.id)).limit(30).all()
    .find((j) => !(parseJson<any>(j.payload, {}).mediaIds ?? []).length);
  const result = index ? parseJson<any>(index.result, {}) : {};
  const warnings: string[] = result?.warnings ?? [];
  const byTitle = (title: string) => media_rows.filter((m) => m.title === title).sort((a, b) => Number(a.type === 'Book') - Number(b.type === 'Book'))[0];
  const media_rows = db.select({ id: media.id, title: media.title, type: media.type, localRoot: media.localRoot }).from(media).all();
  const pinned = new Set(media_rows.filter((m) => m.localRoot).map((m) => m.id));
  const checkList: { mediaId: number | null; title: string; why: string; folders: string[] }[] = result?.summary?.checkList
    ?? warnings.filter((w) => w.startsWith('check: ')).map((w) => {
      const m = /^check: (.*) \((year|ambiguous|pinned folder missing)\): (.*)$/.exec(w);
      return m ? { mediaId: byTitle(m[1])?.id ?? null, title: m[1], why: m[2], folders: m[3].split(', ') } : { mediaId: null, title: w.slice(7), why: '', folders: [] };
    });
  const files = {
    checks: checkList.filter((c) => !(c.mediaId && pinned.has(c.mediaId))),
    missing: warnings.filter((w) => w.startsWith('not on the disk: ')).flatMap((w) => w.slice(17).split(', ')).filter((t) => !pinned.has(byTitle(t)?.id ?? -1)),
    at: index?.finishedAt ?? null,
  };
  return { jobs, identity, missing, flagged, auto, files };
}

/** The number in the header's "Review" link: things that need a decision (auto-added instances are informational). */
export function reviewCount(db: Db): number {
  const r = reviewItems(db);
  return r.jobs.length + r.identity.length + r.missing.length + r.flagged.length;
}
