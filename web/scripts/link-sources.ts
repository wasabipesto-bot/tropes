/**
 * Register text sources for works, from a manifest or one at a time.
 *   npx tsx scripts/link-sources.ts data/sources/sources.json   (items[].title + items[].path)
 *   npx tsx scripts/link-sources.ts "Lent" data/sources/epub/Lent.epub
 * Paths are stored as given; the worker resolves them against TROPES_SOURCES_DIR when relative.
 */
import { readFileSync } from 'node:fs';
import { and, eq } from 'drizzle-orm';
import { openDb } from '../src/db/open';
import { localSource, media } from '../src/db/schema';

const db = openDb();
const args = process.argv.slice(2);
const pairs: { title: string; path: string }[] = [];
if (args.length === 1) {
  const manifest = JSON.parse(readFileSync(args[0], 'utf8')) as { items: { title: string; path: string }[] };
  pairs.push(...manifest.items);
} else if (args.length === 2) {
  pairs.push({ title: args[0], path: args[1] });
} else {
  console.error('usage: link-sources.ts <manifest.json> | <title> <path>');
  process.exit(2);
}
let linked = 0, already = 0;
const missing: string[] = [];
for (const { title, path } of pairs) {
  const m = db.select().from(media).where(eq(media.title, title)).get();
  if (!m) { missing.push(title); continue; }
  const exists = db.select().from(localSource).where(and(eq(localSource.mediaId, m.id), eq(localSource.path, path))).get();
  if (exists) { already++; continue; }
  db.insert(localSource).values({ mediaId: m.id, kind: 'text', path }).run();
  linked++;
}
console.log(`linked ${linked}, already linked ${already}, no library entry for ${missing.length}${missing.length ? ': ' + missing.join('; ') : ''}`);
