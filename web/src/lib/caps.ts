import { and, asc, eq, inArray } from 'drizzle-orm';
import type { Db } from '../db/open';
import { evidence, instance } from '../db/schema';

/**
 * Fair-use caps (plan Phase 6, decided 2026-10-19): what anonymous visitors get. Rows over a cap are kept and
 * shown to the owner as "owner only"; they are never deleted. All three are environment-configurable.
 */
export const CAPS = {
  quoteWords: Number(process.env.TROPES_QUOTE_WORDS ?? 100),
  framesPerWorkTrope: Number(process.env.TROPES_FRAMES_PER_WORK_TROPE ?? 10),
  clipSeconds: Number(process.env.TROPES_CLIP_SECONDS ?? 30),
};

export function wordCount(s: string): number {
  return s.split(/\s+/).filter(Boolean).length;
}

/** Recompute the public flag for every evidence row of this instance's trope on its subject (the cap is per work per trope). */
export function applyCaps(db: Db, instanceId: number): void {
  const inst = db.select().from(instance).where(eq(instance.id, instanceId)).get();
  if (!inst) return;
  const siblings = db
    .select({ id: instance.id })
    .from(instance)
    .where(and(eq(instance.tropeId, inst.tropeId), eq(instance.subjectKind, inst.subjectKind), eq(instance.subjectId, inst.subjectId)))
    .all()
    .map((r) => r.id);
  const rows = db.select().from(evidence).where(inArray(evidence.instanceId, siblings)).orderBy(asc(evidence.id)).all();
  let pictures = 0;
  for (const e of rows) {
    let pub: boolean;
    if (e.kind === 'quote') {
      pub = wordCount(e.content ?? '') <= CAPS.quoteWords;
    } else {
      pictures++;
      pub = pictures <= CAPS.framesPerWorkTrope && !(e.kind === 'clip' && e.durationMs != null && e.durationMs > CAPS.clipSeconds * 1000);
    }
    if (pub !== e.public) db.update(evidence).set({ public: pub }).where(eq(evidence.id, e.id)).run();
  }
}

/** The evidence a visitor may see: everything for the owner, public rows otherwise. */
export function visibleEvidence<T extends { public: boolean }>(rows: T[], owner: boolean): T[] {
  return owner ? rows : rows.filter((e) => e.public);
}
