/**
 * Load seed tropes, series and instances from seed/tropes.json.
 *   npx tsx scripts/seed.ts [--replace] [--dry-run]
 * Tropes that already exist are skipped unless --replace, which deletes the
 * trope (and its instances) and loads it again. Series members are added if
 * missing. Titles that do not resolve to a library entry are reported.
 */
import { readFileSync } from 'node:fs';
import { and, eq } from 'drizzle-orm';
import { openDb } from '../src/db/open';
import { evidence, instance, media, notable, series, seriesMember, trope, tropeSeed, type Prominence } from '../src/db/schema';
import { resolveSubject } from '../src/lib/queries';
import { slugify } from '../src/lib/slug';

interface SeedEvidence { kind: 'quote'; content: string; locator?: string }
interface SeedInstance { subject: string; who?: string; text: string; prominence: Prominence; verified?: boolean; evidence?: SeedEvidence[] }
interface SeedTrope { name: string; description: string; seeds?: string[]; notable?: string[]; instances: SeedInstance[] }
interface SeedSeries { name: string; description?: string; members: string[] }
interface SeedFile { series: SeedSeries[]; tropes: SeedTrope[] }

const args = process.argv.slice(2);
const replace = args.includes('--replace');
const dryRun = args.includes('--dry-run');
const file = args.find((a) => !a.startsWith('--')) ?? 'seed/tropes.json';
const data = JSON.parse(readFileSync(file, 'utf8')) as SeedFile;
const db = openDb();

const unresolved: string[] = [];
const stats = { series: 0, members: 0, tropes: 0, skipped: 0, instances: 0, evidence: 0 };

function findMedia(title: string) {
  return db.select().from(media).where(eq(media.title, title)).get();
}

function run() {
  for (const s of data.series) {
    const slug = slugify(s.name);
    let row = db.select().from(series).where(eq(series.slug, slug)).get();
    if (!row) {
      row = db.insert(series).values({ name: s.name, slug, description: s.description ?? null }).returning().get();
      stats.series++;
    }
    s.members.forEach((title, i) => {
      const m = findMedia(title);
      if (!m) return unresolved.push(`${title} (member of ${s.name})`);
      const exists = db.select().from(seriesMember).where(and(eq(seriesMember.seriesId, row!.id), eq(seriesMember.mediaId, m.id))).get();
      if (!exists) {
        db.insert(seriesMember).values({ seriesId: row!.id, mediaId: m.id, position: i }).run();
        stats.members++;
      }
    });
  }

  for (const t of data.tropes) {
    const slug = slugify(t.name);
    const existing = db.select().from(trope).where(eq(trope.slug, slug)).get();
    if (existing && !replace) { stats.skipped++; continue; }
    if (existing) db.delete(trope).where(eq(trope.id, existing.id)).run();
    const row = db.insert(trope).values({ name: t.name, slug, description: t.description }).returning().get();
    stats.tropes++;
    for (const title of t.seeds ?? []) {
      const subject = resolveSubject(db, title);
      db.insert(tropeSeed).values({ tropeId: row.id, title, mediaId: subject?.kind === 'media' ? subject.id : null }).run();
    }
    const bySubject = new Map<string, number>();
    for (const i of t.instances) {
      const subject = resolveSubject(db, i.subject.replace(/^series:/, ''));
      if (!subject) { unresolved.push(`${i.subject} (${t.name})`); continue; }
      const created = db
        .insert(instance)
        .values({ tropeId: row.id, subjectKind: subject.kind, subjectId: subject.id, who: i.who ?? '', text: i.text, prominence: i.prominence, verified: i.verified ?? false, origin: 'manual' })
        .returning()
        .get();
      stats.instances++;
      bySubject.set(i.subject.replace(/^series:/, ''), created.id);
      (i.evidence ?? []).forEach((e, pos) => {
        db.insert(evidence).values({ instanceId: created.id, kind: e.kind, content: e.content, locator: e.locator ?? '', position: pos }).run();
        stats.evidence++;
      });
    }
    (t.notable ?? []).forEach((title, pos) => {
      const id = bySubject.get(title);
      if (id) db.insert(notable).values({ tropeId: row.id, instanceId: id, position: pos }).run();
      else unresolved.push(`${title} (notable, ${t.name})`);
    });
  }
}

if (dryRun) {
  // Run inside a transaction and roll it back by throwing.
  try { db.transaction(() => { run(); throw new Error('dry-run'); }); } catch (e) { if ((e as Error).message !== 'dry-run') throw e; }
} else {
  db.transaction(run);
}

console.log(`${dryRun ? '[dry run] ' : ''}series +${stats.series} (members +${stats.members}), tropes +${stats.tropes} (skipped ${stats.skipped}), instances +${stats.instances}, evidence +${stats.evidence}`);
if (unresolved.length) {
  console.log('unresolved:');
  for (const u of unresolved) console.log(`  ${u}`);
}
