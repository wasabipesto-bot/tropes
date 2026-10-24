/**
 * The automatic path for Notion-synced entries (plan T14). The sync inserts
 * rows; this module decides what to queue next and, as later jobs finish,
 * what to commit without review. Everything it commits is marked as such
 * (unverified instances, model descriptions), and anything uncertain goes to
 * /review instead.
 */
import { eq, inArray } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { media } from '../../db/schema';
import type { ImportReport } from '../notion-import';
import { createJob } from './queue';

/** After a sync: look up new entries; re-fetch posters when an Image Link changed; flag a changed Media Link on a pinned match. */
export function afterNotionSync(db: Db, report: ImportReport): { lookups: number; refreshes: number; flagged: number } {
  const out = { lookups: 0, refreshes: 0, flagged: 0 };
  if (report.insertedIds.length > 0) {
    createJob(db, 'lookup_media', { mediaIds: report.insertedIds, auto: true });
    out.lookups = report.insertedIds.length;
  }
  const changed = report.changes.filter((c) => c.fields.includes('notionImageUrl') || c.fields.includes('notionMediaUrl'));
  if (changed.length === 0) return out;
  const rows = db.select().from(media).where(inArray(media.id, changed.map((c) => c.id))).all();
  const refresh: number[] = [];
  for (const c of changed) {
    const m = rows.find((r) => r.id === c.id);
    if (!m) continue;
    if (c.fields.includes('notionImageUrl') && m.identity === 'pinned') refresh.push(m.id);
    if (c.fields.includes('notionMediaUrl') && m.identity === 'pinned') {
      db.update(media).set({ reviewNote: 'The Media Link in Notion changed after this match was pinned.' }).where(eq(media.id, m.id)).run();
      out.flagged++;
    }
  }
  if (refresh.length > 0) {
    createJob(db, 'lookup_media', { mediaIds: refresh, auto: true, refresh: true });
    out.refreshes = refresh.length;
  }
  return out;
}
