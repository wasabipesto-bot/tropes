/**
 * The automatic path for Notion-synced entries (plan T14). The sync inserts
 * rows; this module decides what to queue next and, as later jobs finish,
 * what to commit without review. Everything it commits is marked as such
 * (unverified instances, model descriptions), and anything uncertain goes to
 * /review instead.
 */
import { and, eq, inArray, isNull, sql } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { dossier, job, localSource, media, mediaNote, proposal, trope, type Job, type Proposal } from '../../db/schema';
import { commitMatch, recordUnresolved, syncNotionLink, type MatchPayload } from '../metadata';
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
    createJob(db, 'index_local', { mediaIds: report.insertedIds, auto: true });
    out.lookups = report.insertedIds.length;
  }
  const changed = report.changes.filter((c) => c.fields.includes('notionImageUrl') || c.fields.includes('notionMediaUrl'));
  if (changed.length === 0) return out;
  const rows = db.select().from(media).where(inArray(media.id, changed.map((c) => c.id))).all();
  const refresh: number[] = [];
  for (const c of changed) {
    const m = rows.find((r) => r.id === c.id);
    if (!m) continue;
    if (c.fields.includes('notionMediaUrl')) syncNotionLink(db, m.id);
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
  if (j.kind === 'scan_trope' || j.kind === 'check_subject' || j.kind === 'find_evidence' || j.kind === 'draft_instance') queueFrames(db, j);
  if (j.kind === 'find_evidence' || j.kind === 'draft_instance') {
    // The owner asked for these by name, so they go straight onto the instance; Remove is one click away.
    const rows = db.select({ id: proposal.id }).from(proposal).where(and(eq(proposal.jobId, j.id), eq(proposal.kind, 'evidence'))).all();
    if (rows.length > 0) commitProposals(db, j.id, new Set(rows.map((r) => r.id)), {});
    return;
  }
  if (j.kind === 'extract_evidence' && payload.forJob) {
    // Frames for a scan: visual tropes get the model's look before the proposals are shown or committed (plan D12).
    const scan = db.select().from(job).where(eq(job.id, payload.forJob)).get();
    if (scan && visualProposals(db, scan).length > 0) createJob(db, 'look_frames', { forJob: scan.id, auto: Boolean(parseJson<any>(scan.payload, {}).auto) });
    return;
  }
  if (j.kind === 'look_frames' && payload.auto) {
    // The automatic path held these back until the look landed.
    const scan = db.select().from(job).where(eq(job.id, payload.forJob)).get();
    if (scan?.kind === 'check_subject') autoCommit(db, scan, (p) => parseJson<any>(p.payload, {}).look?.seen !== false);
    return;
  }
  if (!payload.auto) return;
  if (CHAIN.includes(j.kind)) {
    continueChain(db, j, payload);
    return;
  }
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
    if (payload.refresh) {
      // New files on the disk: only the works whose dossier actually changed get a recheck.
      const rebuilt = db.select({ id: dossier.subjectId }).from(dossier).where(and(eq(dossier.subjectKind, 'media'), inArray(dossier.subjectId, ids), sql`${dossier.builtAt} >= ${j.createdAt}`)).all();
      for (const r of rebuilt) createJob(db, 'check_subject', { mode: 'recheck', subject: { kind: 'media', id: r.id }, auto: true });
      return;
    }
    const empty = db.select({ id: media.id }).from(media).where(and(inArray(media.id, ids), isNull(media.description))).all().map((r) => r.id);
    if (empty.length > 0) createJob(db, 'write_blurbs', { mediaIds: empty, auto: true });
    for (const id of ids.filter((x) => !empty.includes(x))) createJob(db, 'check_subject', { mode: 'add', subject: { kind: 'media', id }, auto: true });
  } else if (j.kind === 'write_blurbs') {
    for (const id of payload.mediaIds ?? []) createJob(db, 'check_subject', { mode: 'add', subject: { kind: 'media', id }, auto: true });
  } else if (j.kind === 'check_subject') {
    // Proposals for visual tropes with frames on the way wait for the look (plan D12); the rest go in now.
    const waiting = new Set(visualProposals(db, j).filter((p) => parseJson<any[]>(p.evidence, []).some((e) => typeof e.at === 'number')).map((p) => p.id));
    autoCommit(db, j, (p) => !waiting.has(p.id));
  }
}

const CHAIN = ['index_local', 'extract_text', 'make_sheets', 'read_sheets'];

/**
 * The disk chain (plan T2, D11): index → text → contact sheets → visual notes, each stage only for what is new,
 * stages with nothing to do skipped. With `then: 'dossier'` (the Refresh button, or the weekly index when
 * TROPES_AUTO_DOSSIER is on) it goes on to rebuild the dossiers whose text changed and recheck their tropes.
 */
function continueChain(db: Db, j: Job, payload: any): void {
  const ids: number[] | undefined = payload.mediaIds?.length ? payload.mediaIds : undefined;
  const ctx = { auto: true, ...(payload.then ? { then: payload.then } : {}), ...(ids ? { mediaIds: ids } : {}) };
  const rows = ids
    ? db.select().from(localSource).where(and(inArray(localSource.mediaId, ids), inArray(localSource.kind, ['video', 'book']))).all()
    : db.select().from(localSource).where(inArray(localSource.kind, ['video', 'book'])).all();
  const noted = new Set(db.select({ mediaId: mediaNote.mediaId, label: mediaNote.label }).from(mediaNote).where(eq(mediaNote.source, 'visual')).all().map((n) => `${n.mediaId}:${n.label}`));
  const todo: Record<string, () => number[]> = {
    extract_text: () => rows.filter((s) => !s.indexedAt).map((s) => s.id),
    make_sheets: () => rows.filter((s) => s.kind === 'video' && !parseJson<any>(s.meta, {}).sheets).map((s) => s.id),
    read_sheets: () => rows.filter((s) => s.kind === 'video' && parseJson<any>(s.meta, {}).sheets && !noted.has(`${s.mediaId}:${s.label}`)).map((s) => s.id),
  };
  for (let stage = CHAIN.indexOf(j.kind) + 1; stage < CHAIN.length; stage++) {
    const kind = CHAIN[stage] as 'extract_text' | 'make_sheets' | 'read_sheets';
    // Reading sheets costs model money per sheet: the chain does it for named works (a refresh, new entries),
    // never for the whole disk from the timer; the library-wide read is queued by hand.
    if (kind === 'read_sheets' && !ids) continue;
    const sourceIds = todo[kind]();
    if (sourceIds.length > 0) {
      createJob(db, kind, { sourceIds, ...ctx });
      return;
    }
  }
  if (payload.then === 'dossier') {
    const subjects = [...new Set(rows.map((s) => s.mediaId))].map((id) => ({ kind: 'media' as const, id }));
    if (subjects.length > 0) createJob(db, 'build_dossiers', { onlyMissing: true, subjects, auto: true, refresh: true });
  }
}

/** Commit the scan's instance proposals at or over the cut that pass `keep`, unverified, leaving the rest pending. */
function autoCommit(db: Db, j: Job, keep: (p: Proposal) => boolean): void {
  const min = autoCommitMin();
  const rows = db.select().from(proposal).where(and(eq(proposal.jobId, j.id), eq(proposal.kind, 'instance'), eq(proposal.decision, 'pending'))).all();
  const accepted = new Set(rows.filter((p) => p.score >= min && keep(p)).map((p) => p.id));
  if (accepted.size > 0) commitProposals(db, j.id, accepted, {}, { verified: false, rejectRest: false });
}

/** A scan's proposals whose trope is marked "Visual trope, use screenshots" (a draft carries the flag in the payload). */
function visualProposals(db: Db, scan: Job): Proposal[] {
  const payload = parseJson<any>(scan.payload, {});
  const rows = db.select().from(proposal).where(and(eq(proposal.jobId, scan.id), eq(proposal.kind, 'instance'))).all();
  if (rows.length === 0) return [];
  const visual = new Set(db.select({ id: trope.id }).from(trope).where(eq(trope.visual, true)).all().map((t) => t.id));
  return rows.filter((p) => (p.tropeId ? visual.has(p.tropeId) : Boolean(payload.draft?.visual)));
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

/** Quotes with a timestamp get a frame grabbed right after the scan, so the review page shows the picture with the quote (plan D9). */
export function queueFrames(db: Db, j: Job): number {
  const rows = db.select().from(proposal).where(eq(proposal.jobId, j.id)).all();
  const items: { proposalId: number; sourceId: number; at: number; end?: number }[] = [];
  for (const p of rows) {
    if (p.subjectKind !== 'media') continue;
    const quotes = parseJson<any[]>(p.evidence, []).filter((e) => typeof e.at === 'number' && !e.frame);
    if (quotes.length === 0) continue;
    const sources = db.select().from(localSource).where(and(eq(localSource.mediaId, p.subjectId), eq(localSource.kind, 'video'))).all();
    for (const q of quotes) {
      const label = String(q.locator ?? '').split(' ')[0];
      const src = sources.find((s) => s.label === (/^S\d+E\d+$/.test(label) ? label : ''));
      if (src) items.push({ proposalId: p.id, sourceId: src.id, at: q.at, ...(q.end ? { end: q.end } : {}) });
    }
  }
  if (items.length > 0) createJob(db, 'extract_evidence', { items, forJob: j.id });
  return items.length;
}
