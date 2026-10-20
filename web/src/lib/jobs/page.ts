import type { AstroGlobal } from 'astro';
import type { Db } from '../../db/open';
import type { Job } from '../../db/schema';
import { jobById, parseJson } from './queue';

/** Shared bits for the four review pages: the job from ?job=, the editing id from ?edit=, the summary. */
export function reviewState(Astro: AstroGlobal, db: Db) {
  const p = Astro.url.searchParams;
  const jobId = /^\d+$/.test(p.get('job') ?? '') ? Number(p.get('job')) : null;
  const j: Job | undefined = jobId ? jobById(db, jobId) : undefined;
  const editing = /^\d+$/.test(p.get('edit') ?? '') ? Number(p.get('edit')) : null;
  const added = /^\d+$/.test(p.get('added') ?? '') ? Number(p.get('added')) : null;
  const summary = j ? parseJson<any>(j.result, {})?.summary ?? {} : {};
  const warnings: string[] = j ? parseJson<any>(j.result, {})?.warnings ?? [] : [];
  const returnTo = Astro.url.pathname + (jobId ? `?job=${jobId}` : '');
  return { jobId, job: j, editing, added, summary, warnings, returnTo };
}
