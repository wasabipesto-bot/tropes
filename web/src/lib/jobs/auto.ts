/**
 * The automatic path for Notion-synced entries (plan T14). The sync inserts
 * rows; this module decides what to queue next and, as later jobs finish,
 * what to commit without review. Everything it commits is marked as such
 * (unverified instances, model descriptions), and anything uncertain goes to
 * /review instead.
 */
import { and, eq, inArray, isNull, sql } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { dossier, media, proposal, type Job } from '../../db/schema';
import { commitMatch, recordUnresolved, type MatchPayload } from '../metadata';
import type { ImportReport } from '../notion-import';
import { commitProposals } from './commit';
import { createJob, parseJson } from './queue';

/** Proposals scoring at least this are committed without review on the automatic path (plan D23; 0.5 is the review cut). */
export function autoCommitMin(): number {
  const n = Number(process.env.TROPES_AUTO_COMMIT_MIN ?? '0.7');
  return Number.isFinite(n) ? n : 0.7;
}

/** After a sync: look up new entries; re-fetch posters when an Image Link changed; flag a changed Media Link on a pinned match. */
export function afterNotionSync(db: Db, report: ImportReport): { lookups: number; refreshes: number; flagged: number } {
  const out = { lookups: 0, refreshes: 0, flagged: 0 };
  if (report.insertedIds.length > 0) {
    createJob(db, 'lookup_media', { mediaIds: report.insertedIds, auto: true });
    out.lookups = report.insertedIds.length;
  }
  const changed = report.changes.filter((c) => c.fields.includes('notionImageUrl') || c.fields.includes('notionMediaUrl'));
  if (changed.length === 0) return out;
  const rows = db.select().from(media).where(inArray(media.id, changed.map((c) => c.id))).all();
  const refresh: number[] = [];
  for (const c of changed) {
    const m = rows.find((r) => r.id === c.id);
    if (!m) continue;
    if (c.fields.includes('notionImageUrl') && m.identity === 'pinned') refresh.push(m.id);
    if (c.fields.includes('notionMediaUrl') && m.identity === 'pinned') {
      db.update(media).set({ reviewNote: 'The Media Link in Notion changed after this match was pinned.' }).where(eq(media.id, m.id)).run();
      out.flagged++;
    }
  }
  if (refresh.length > 0) {
    createJob(db, 'lookup_media', { mediaIds: refresh, auto: true, refresh: true });
    out.refreshes = refresh.length;
  }
  return out;
}

/**
 * The chain after a job on the automatic path finishes:
 * lookup (confident matches committed, the rest recorded for /review) → dossiers → blurbs → trope check (≥ cut committed, unverified).
 */
export function afterJobDone(db: Db, j: Job): void {
  const payload = parseJson<any>(j.payload, {});
  if (j.kind === 'lookup_media') supersedeOlderMatches(db, j, payload.mediaIds ?? []);
  if (!payload.auto) return;
  if (j.kind === 'lookup_media') {
    const rows = db.select().from(proposal).where(and(eq(proposal.jobId, j.id), eq(proposal.kind, 'match'))).all();
    for (const p of rows) {
      const mp = parseJson<MatchPayload | null>(p.payload, null);
      if (!mp) continue;
      if (mp.status === 'confident' && mp.chosen) {
        commitMatch(db, p.subjectId, mp);
        db.update(proposal).set({ decision: 'accepted' }).where(eq(proposal.id, p.id)).run();
      } else {
        recordUnresolved(db, p.subjectId, mp);
      }
    }
    // New entries go on to dossiers, a blurb and the trope check; a re-lookup of a known entry stops here.
    const known = new Set(db.select({ id: dossier.subjectId }).from(dossier).where(eq(dossier.subjectKind, 'media')).all().map((r) => r.id));
    const fresh: number[] = (payload.mediaIds ?? []).filter((id: number) => !known.has(id));
    if (!payload.refresh && fresh.length > 0) {
      createJob(db, 'build_dossiers', { onlyMissing: true, subjects: fresh.map((id: number) => ({ kind: 'media', id })), auto: true });
    }
  } else if (j.kind === 'build_dossiers') {
    const ids: number[] = (payload.subjects ?? []).filter((s: any) => s.kind === 'media').map((s: any) => s.id);
    if (ids.length === 0) return;
    const empty = db.select({ id: media.id }).from(media).where(and(inArray(media.id, ids), isNull(media.description))).all().map((r) => r.id);
    if (empty.length > 0) createJob(db, 'write_blurbs', { mediaIds: empty, auto: true });
    for (const id of ids.filter((x) => !empty.includes(x))) createJob(db, 'check_subject', { mode: 'add', subject: { kind: 'media', id }, auto: true });
  } else if (j.kind === 'write_blurbs') {
    for (const id of payload.mediaIds ?? []) createJob(db, 'check_subject', { mode: 'add', subject: { kind: 'media', id }, auto: true });
  } else if (j.kind === 'check_subject') {
    const min = autoCommitMin();
    const rows = db.select().from(proposal).where(and(eq(proposal.jobId, j.id), eq(proposal.kind, 'instance'))).all();
    const accepted = new Set(rows.filter((p) => p.score >= min).map((p) => p.id));
    commitProposals(db, j.id, accepted, {}, { verified: false, rejectRest: false });
  }
}

/** A newer lookup of the same entries replaces older matches still waiting for a decision (Phase 3's discard rule). */
function supersedeOlderMatches(db: Db, j: Job, mediaIds: number[]): void {
  if (mediaIds.length === 0) return;
  const older = db
    .select({ id: proposal.id })
    .from(proposal)
    .where(and(eq(proposal.kind, 'match'), eq(proposal.decision, 'pending'), inArray(proposal.subjectId, mediaIds), sql`${proposal.jobId} < ${j.id}`))
    .all();
  if (older.length > 0) db.update(proposal).set({ decision: 'rejected' }).where(inArray(proposal.id, older.map((o) => o.id))).run();
}
