/**
 * Before/after table for a dossier rebuild: npx tsx scripts/compare-dossiers.ts <dir-with-before/> [idsCsv]
 * Writes <dir>/after/<id>.json from the live database and prints a Markdown table.
 */
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { and, eq } from 'drizzle-orm';
import { openDb } from '../src/db/open';
import { dossier, media } from '../src/db/schema';

const dir = process.argv[2];
if (!dir) { console.error('usage: compare-dossiers.ts <dir>'); process.exit(2); }
const db = openDb();
mkdirSync(join(dir, 'after'), { recursive: true });
const count = (b: any) => ({ chars: b?.characters?.length ?? 0, motifs: b?.motifs?.length ?? 0, scenes: b?.notable_scenes?.length ?? 0, arcs: b?.arcs?.length ?? 0 });
const located = (b: any) => { const xs = [...(b?.notable_scenes ?? []), ...(b?.arcs ?? [])]; return xs.length ? Math.round((100 * xs.filter((x: any) => x.locator).length) / xs.length) : 0; };
const rows: string[] = ['| Work | Before (depth/known) | After | Characters | Motifs | Scenes | Arcs | Located % | Words read |', '|---|---|---|---|---|---|---|---|---|'];
for (const f of readdirSync(join(dir, 'before')).filter((x) => x.endsWith('.json')).sort((a, b) => Number(a.split('.')[0]) - Number(b.split('.')[0]))) {
  const before = JSON.parse(readFileSync(join(dir, 'before', f), 'utf8'));
  const id = Number(f.split('.')[0]);
  const d = db.select().from(dossier).where(and(eq(dossier.subjectKind, 'media'), eq(dossier.subjectId, id))).get();
  const m = db.select().from(media).where(eq(media.id, id)).get()!;
  const body = d ? JSON.parse(d.body) : null;
  const inputs = d ? JSON.parse(d.inputs || '{}') : {};
  writeFileSync(join(dir, 'after', f), JSON.stringify({ id, title: m.title, depth: d?.depth, model: d?.model, builtAt: d?.builtAt, inputs, body }, null, 2));
  const b0 = count(before.body), b1 = count(body);
  const fmt = (a: number, b: number) => `${a} → ${b}`;
  rows.push(`| ${m.title} | ${before.depth ?? '—'}/${before.body?.known ?? '—'} | ${d?.depth ?? '—'}/${body?.known ?? '—'} | ${fmt(b0.chars, b1.chars)} | ${fmt(b0.motifs, b1.motifs)} | ${fmt(b0.scenes, b1.scenes)} | ${fmt(b0.arcs, b1.arcs)} | ${located(before.body)} → ${located(body)} | ${inputs.text?.words ? Number(inputs.text.words).toLocaleString('en-GB') : inputs.visual ? `visual notes ×${inputs.visual}` : '—'}${inputs.blocks ? ` (${inputs.blocks} blocks)` : ''} |`);
}
console.log(rows.join('\n'));
