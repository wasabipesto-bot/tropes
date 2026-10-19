/**
 * Import a Notion CSV export into the site database.
 *   npx tsx scripts/import.ts path/to/export.csv [--dry-run]
 * Uses DATABASE_PATH (default ./data/tropes.db).
 */
import { readFileSync } from 'node:fs';
import { openDb } from '../src/db/open';
import { importCsv } from '../src/lib/notion-import';

const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const file = args.find((a) => !a.startsWith('--'));
if (!file) {
  console.error('usage: import.ts <export.csv> [--dry-run]');
  process.exit(2);
}
const db = openDb();
const report = importCsv(db, readFileSync(file, 'utf8'), { dryRun });
console.log(`${dryRun ? '[dry run] ' : ''}inserted ${report.inserted}, updated ${report.updated}, unchanged ${report.unchanged}, skipped ${report.skipped.length}`);
for (const s of report.skipped) console.log(`  skipped line ${s.line}: ${s.reason}`);
if (report.duplicates.length) console.log(`  duplicate title+type in file: ${report.duplicates.join('; ')}`);
