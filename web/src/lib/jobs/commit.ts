import { and, eq, sql } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { evidence, instance, job, proposal, trope, tropeSeed, type Prominence } from '../../db/schema';
import { resolveSubject } from '../queries';
import { slugify } from '../slug';
import { parseJson } from './queue';

export interface CommitOptions {
  /** The owner reviewed these, so they are verified (plan T16). The automatic path passes false. */
  verified?: boolean;
  /** Mark everything not accepted as rejected (the owner's review). The automatic path leaves the rest pending for /review. */
  rejectRest?: boolean;
}

/**
 * Turn a job's accepted proposals into instances and evidence. For an add-trope
 * job the trope row is created here, which is the first moment anything is saved.
 */
export function commitProposals(db: Db, jobId: number, accepted: Set<number>, prominence: Record<string, Prominence>, opts: CommitOptions = {}): { returnTo: string; created: number } {
  const verified = opts.verified ?? true;
  const rejectRest = opts.rejectRest ?? true;
  return db.transaction((tx) => {
    const j = tx.select().from(job).where(eq(job.id, jobId)).get();
    if (!j || j.status !== 'done') throw new Error('That scan is no longer open.');
    const payload = parseJson<any>(j.payload, {});
    let tropeId: number | null = payload.tropeId ?? null;
    let returnTo = '/tropes';

    if (j.kind === 'scan_trope' && !tropeId) {
      const d = payload.draft;
      const slug = slugify(d.name);
      const existing = tx.select().from(trope).where(eq(trope.slug, slug)).get();
      const row = existing ?? tx.insert(trope).values({ name: d.name, slug, description: d.description }).returning().get();
      tropeId = row.id;
      if (!existing) {
        for (const title of d.seeds ?? []) {
          const subject = resolveSubject(tx as unknown as Db, title);
          tx.insert(tropeSeed).values({ tropeId: row.id, title, mediaId: subject?.kind === 'media' ? subject.id : null }).run();
        }
      }
      returnTo = `/tropes/${slug}`;
    } else if (j.kind === 'scan_trope') {
      const t = tx.select().from(trope).where(eq(trope.id, tropeId!)).get();
      returnTo = t ? `/tropes/${t.slug}` : '/tropes';
    } else if (j.kind === 'check_subject') {
      const s = payload.subject;
      returnTo = s.kind === 'media' ? `/media/${s.id}` : `/series/${s.id}`;
    }

    const rows = tx.select().from(proposal).where(eq(proposal.jobId, jobId)).all();
    let created = 0;
    for (const p of rows) {
      if (p.kind === 'match') continue; // metadata matches are committed from /metadata, not here
      const take = accepted.has(p.id);
      const tId = p.tropeId ?? tropeId;
      if (take && tId) {
        if (p.kind === 'instance') {
          const already = tx.select().from(instance).where(and(eq(instance.tropeId, tId), eq(instance.subjectKind, p.subjectKind), eq(instance.subjectId, p.subjectId))).get();
          const inst = already ?? tx
            .insert(instance)
            .values({ tropeId: tId, subjectKind: p.subjectKind, subjectId: p.subjectId, who: p.who, text: p.text, prominence: prominence[String(p.id)] ?? p.prominence, verified, score: p.score, origin: 'model' })
            .returning()
            .get();
          addEvidence(tx as unknown as Db, inst.id, parseJson<any[]>(p.evidence, []));
          if (!already) created++;
        } else if (p.kind === 'evidence' && p.targetInstanceId) {
          addEvidence(tx as unknown as Db, p.targetInstanceId, parseJson<any[]>(p.evidence, []));
          created++;
        }
      }
      if (take || rejectRest) tx.update(proposal).set({ decision: take ? 'accepted' : 'rejected', tropeId: tId ?? null }).where(eq(proposal.id, p.id)).run();
      else if (tId && !p.tropeId) tx.update(proposal).set({ tropeId: tId }).where(eq(proposal.id, p.id)).run();
    }
    tx.update(job).set({ result: JSON.stringify({ ...parseJson<any>(j.result, {}), committed: created, committedAt: new Date().toISOString() }) }).where(eq(job.id, jobId)).run();
    return { returnTo: `${returnTo}${returnTo.includes('?') ? '&' : '?'}added=${created}`, created };
  });
}

function addEvidence(tx: Db, instanceId: number, items: { kind?: string; content: string; locator?: string }[]): void {
  if (items.length === 0) return;
  const [{ n }] = tx.select({ n: sql<number>`coalesce(max(${evidence.position}), -1) + 1` }).from(evidence).where(eq(evidence.instanceId, instanceId)).all();
  items.forEach((e, i) => {
    const dup = tx.select().from(evidence).where(and(eq(evidence.instanceId, instanceId), eq(evidence.content, e.content))).get();
    if (dup) return;
    tx.insert(evidence).values({ instanceId, kind: 'quote', content: e.content, locator: e.locator ?? '', position: n + i }).run();
  });
}
