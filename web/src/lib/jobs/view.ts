import { asc, eq, inArray } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { proposal, trope, type Job, type Proposal, type Trope } from '../../db/schema';
import { subjectRef, type SubjectRef } from '../queries';
import { parseJson } from './queue';

export interface ProposalView {
  p: Proposal;
  subject: SubjectRef;
  trope: Trope | null;
  evidence: { kind: string; content: string; locator: string }[];
  flags: string[];
  checked: boolean;
}

/** Proposals of a job ready to render: seeds first, then by score, previously rejected ones last. */
export function proposalsFor(db: Db, j: Job, uncheckedBelow: number): ProposalView[] {
  const rows = db.select().from(proposal).where(eq(proposal.jobId, j.id)).orderBy(asc(proposal.id)).all();
  const tropeIds = [...new Set(rows.map((r) => r.tropeId).filter((x): x is number => x !== null))];
  const tropes = tropeIds.length ? db.select().from(trope).where(inArray(trope.id, tropeIds)).all() : [];
  const views: ProposalView[] = [];
  for (const p of rows) {
    const subject = subjectRef(db, p.subjectKind, p.subjectId);
    if (!subject) continue;
    views.push({ p, subject, trope: tropes.find((t) => t.id === p.tropeId) ?? null, evidence: parseJson(p.evidence, []), flags: parseJson(p.flags, []), checked: p.decision === 'accepted' || (p.decision === 'pending' && !p.rejectedBefore && p.score >= uncheckedBelow) });
  }
  return views.sort((a, b) => Number(a.p.rejectedBefore) - Number(b.p.rejectedBefore) || Number(b.p.seed) - Number(a.p.seed) || b.p.score - a.p.score);
}

/** "Found all three of your examples, scoring 0.97, 0.90 and 0.81, plus four others. Anything under 0.5 starts unchecked." */
export function calibrationLine(summary: any, uncheckedBelow: number): string {
  const allSeeds: { title: string; found: boolean; score: number | null; resolved: boolean; attached?: boolean }[] = summary?.seeds ?? [];
  const attached = allSeeds.filter((s) => s.attached);
  const seeds = allSeeds.filter((s) => !s.attached);
  const others = Math.max(0, (summary?.proposals ?? 0) - seeds.filter((s) => s.found).length);
  const words = ['none', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
  const n = (k: number) => words[k] ?? String(k);
  const parts: string[] = [];
  if (seeds.length > 0) {
    const found = seeds.filter((s) => s.found);
    const scores = found.map((s) => (s.score ?? 0).toFixed(2));
    const list = scores.length > 1 ? `${scores.slice(0, -1).join(', ')} and ${scores[scores.length - 1]}` : scores[0];
    const all = seeds.length === 1 ? 'your example' : seeds.length === 2 ? 'both of your examples' : `all ${n(seeds.length)} of your examples`;
    if (found.length === seeds.length) parts.push(`Found ${all}${scores.length ? `, scoring ${list}` : ''}`);
    else if (found.length === 0) parts.push(`Found none of your ${n(seeds.length)} examples`);
    else parts.push(`Found ${n(found.length)} of your ${n(seeds.length)} examples, scoring ${list}`);
    const missing = seeds.filter((s) => !s.resolved).map((s) => s.title);
    parts.push(others > 0 ? `, plus ${n(others)} other${others === 1 ? '' : 's'}.` : '.');
    if (missing.length) parts.push(` Not in the library: ${missing.join(', ')}.`);
  } else if (attached.length > 0) {
    parts.push(`${attached.length === 1 ? 'Your example is' : `All ${n(attached.length)} of your examples are`} already attached${others > 0 ? `, plus ${n(others)} other${others === 1 ? '' : 's'} proposed` : ''}.`);
  } else {
    parts.push(`${summary?.proposals ?? 0} proposals.`);
  }
  parts.push(` Anything under ${uncheckedBelow} starts unchecked.`);
  return parts.join('');
}

export const UNCHECKED_BELOW = 0.5;
