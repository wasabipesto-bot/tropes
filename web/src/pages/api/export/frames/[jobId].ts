import type { APIRoute } from 'astro';
import { eq } from 'drizzle-orm';
import { db } from '../../../../db';
import { job, proposal, trope } from '../../../../db/schema';
import { parseJson } from '../../../../lib/jobs/queue';
import { unauthorized, workerAuthorized } from '../../../../lib/worker-auth';

/**
 * For look_frames (plan D12): a scan's proposals for visual tropes that have frames waiting, with the trope's
 * description and each frame's file name under /evidence/pending/<proposal>/.
 */
export const GET: APIRoute = ({ request, params }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const j = db.select().from(job).where(eq(job.id, Number(params.jobId))).get();
  if (!j) return Response.json({ error: 'no such job' }, { status: 404 });
  const payload = parseJson<any>(j.payload, {});
  const tropes = new Map(db.select().from(trope).all().map((t) => [t.id, t]));
  const items = db.select().from(proposal).where(eq(proposal.jobId, j.id)).all().flatMap((p) => {
    const t = p.tropeId ? tropes.get(p.tropeId) : null;
    const visual = t ? t.visual : Boolean(payload.draft?.visual);
    if (!visual) return [];
    const frames = parseJson<any[]>(p.evidence, []).filter((e) => e.frame).map((e) => ({ name: e.frame as string, locator: e.locator ?? '', content: e.content ?? '' }));
    if (frames.length === 0) return [];
    return [{ proposalId: p.id, trope: { name: t?.name ?? payload.draft?.name ?? '', description: t?.description ?? payload.draft?.description ?? '' }, who: p.who, text: p.text, frames }];
  });
  return Response.json({ items });
};
