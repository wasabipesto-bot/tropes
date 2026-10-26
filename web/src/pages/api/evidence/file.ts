import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import type { APIRoute } from 'astro';
import { eq } from 'drizzle-orm';
import { db } from '../../../db';
import { evidence, proposal } from '../../../db/schema';
import { applyCaps } from '../../../lib/caps';
import { evidencePath, pendingEvidencePath } from '../../../lib/files';
import { parseJson } from '../../../lib/jobs/queue';
import { badRequest, unauthorized, workerAuthorized } from '../../../lib/worker-auth';

const MAX = { frame: 2_000_000, clip: 40_000_000 } as const;

/**
 * The media worker uploads a frame (WebP) or clip (mp4) for a quote. `target` is `proposal:<id>`,
 * where the file waits in the pending folder and the quote's evidence item gains `frame` or `clip`
 * until the proposal is committed or discarded, or `evidence:<id>`, where the row gets its file at once.
 */
export const POST: APIRoute = async ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const form = await request.formData().catch(() => null);
  if (!form) return badRequest('expected multipart form data');
  const target = String(form.get('target') ?? '');
  const kind = String(form.get('kind') ?? '');
  const at = Number(form.get('at'));
  const file = form.get('file');
  if (!(kind === 'frame' || kind === 'clip') || !(file instanceof File) || !Number.isFinite(at)) return badRequest('expected target, kind, at and a file');
  const buf = Buffer.from(await file.arrayBuffer());
  if (buf.length === 0 || buf.length > MAX[kind]) return badRequest(`bad file size ${buf.length}`);
  const ext = kind === 'frame' ? 'webp' : 'mp4';
  const m = /^(proposal|evidence):(\d+)$/.exec(target);
  if (!m) return badRequest('bad target');
  const id = Number(m[2]);
  if (m[1] === 'proposal') {
    const p = db.select().from(proposal).where(eq(proposal.id, id)).get();
    if (!p) return Response.json({ error: 'no such proposal' }, { status: 404 });
    const items = parseJson<any[]>(p.evidence, []);
    const item = items.find((e) => typeof e.at === 'number' && Math.abs(e.at - at) < 0.01);
    if (!item) return badRequest('no quote at that time');
    const name = `${Math.round(at * 1000)}.${ext}`;
    const path = pendingEvidencePath(id, name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, buf);
    item[kind] = name;
    db.update(proposal).set({ evidence: JSON.stringify(items) }).where(eq(proposal.id, id)).run();
    return Response.json({ stored: 'pending', proposalId: id, name });
  }
  const e = db.select().from(evidence).where(eq(evidence.id, id)).get();
  if (!e) return Response.json({ error: 'no such evidence' }, { status: 404 });
  const rel = `${e.instanceId}/${e.id}.${ext}`;
  const path = evidencePath(rel);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, buf);
  db.update(evidence).set({ filePath: rel, kind: kind === 'frame' ? 'frame' : 'clip' }).where(eq(evidence.id, e.id)).run();
  applyCaps(db, e.instanceId);
  return Response.json({ stored: 'evidence', evidenceId: e.id, path: rel });
};
