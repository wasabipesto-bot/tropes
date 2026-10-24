/**
 * Import the Notion "Media Log" into the media table.
 *
 * Input is a Notion CSV export (its own column names), optionally with a
 * "Notion ID" or "URL" column when the file came from the API rather than
 * the export dialog. Notion owns: title, type, creator, ratings, date, image
 * link, media link. Re-importing overwrites those and leaves every site-only
 * field alone. Rows are matched by Notion id when present, else by exact
 * title and type.
 */
import { and, eq, sql } from 'drizzle-orm';
import type { Db } from '../db/open';
import { MEDIA_TYPES, media, type MediaType, type NewMedia } from '../db/schema';
import { parseCsvRecords } from './csv';

export interface LogRow {
  notionId: string | null;
  title: string;
  type: MediaType;
  creator: string | null;
  loggedDate: string | null;
  ratings: { medium: number | null; story: number | null; tone: number | null; enjoyability: number | null; effect: number | null };
  imageUrl: string | null;
  mediaUrl: string | null;
}

export interface ImportReport {
  inserted: number;
  updated: number;
  unchanged: number;
  skipped: { line: number; reason: string }[];
  duplicates: string[];
  insertedIds: number[];
  /** Updated rows and which Notion-owned fields changed, so the sync can react to a new Image or Media Link. */
  changes: { id: number; fields: string[] }[];
}

const MONTHS: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
  july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
};

/** Notion exports dates as "October 19, 2026" (its "ll" format); the API gives ISO. Both become YYYY-MM-DD. */
export function parseNotionDate(s: string): string | null {
  const t = s.trim();
  if (!t) return null;
  const iso = /^(\d{4}-\d{2}-\d{2})/.exec(t);
  if (iso) return iso[1];
  const long = /^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})/.exec(t);
  if (long) {
    const mo = MONTHS[long[1].toLowerCase()];
    if (mo) return `${long[3]}-${String(mo).padStart(2, '0')}-${long[2].padStart(2, '0')}`;
  }
  const short = /^(\d{4})\/(\d{2})\/(\d{2})/.exec(t);
  if (short) return `${short[1]}-${short[2]}-${short[3]}`;
  return null;
}

function num(s: string | undefined): number | null {
  if (s === undefined) return null;
  const t = s.trim();
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function blank(s: string | undefined): string | null {
  const t = (s ?? '').trim();
  return t === '' ? null : t;
}

function notionIdFrom(rec: Record<string, string>): string | null {
  for (const key of ['Notion ID', 'ID', 'id', 'notion_id', 'URL', 'url']) {
    const v = rec[key];
    if (!v) continue;
    const m = /([0-9a-f]{8})-?([0-9a-f]{4})-?([0-9a-f]{4})-?([0-9a-f]{4})-?([0-9a-f]{12})\s*$/i.exec(v.trim());
    if (m) return (m[1] + m[2] + m[3] + m[4] + m[5]).toLowerCase();
  }
  return null;
}

export function rowsFromCsv(text: string): { rows: LogRow[]; skipped: ImportReport['skipped'] } {
  const rows: LogRow[] = [];
  const skipped: ImportReport['skipped'] = [];
  parseCsvRecords(text).forEach((rec, i) => {
    const line = i + 2;
    const title = blank(rec['Title']);
    const type = blank(rec['Type']);
    if (!title) return skipped.push({ line, reason: 'no title' });
    if (!type || !(MEDIA_TYPES as readonly string[]).includes(type)) return skipped.push({ line, reason: `unknown type "${type ?? ''}" for "${title}"` });
    rows.push({
      notionId: notionIdFrom(rec),
      title,
      type: type as MediaType,
      creator: blank(rec['Artist/Developer']),
      loggedDate: parseNotionDate(rec['Date'] ?? ''),
      ratings: {
        medium: num(rec['Medium']),
        story: num(rec['Story']),
        tone: num(rec['Tone']),
        enjoyability: num(rec['Enjoyability']),
        effect: num(rec['Effect']),
      },
      imageUrl: blank(rec['Image Link']),
      mediaUrl: blank(rec['Media Link']),
    });
  });
  return { rows, skipped };
}

function notionFields(r: LogRow): Omit<NewMedia, 'id'> {
  return {
    notionId: r.notionId,
    title: r.title,
    type: r.type,
    creator: r.creator,
    loggedDate: r.loggedDate,
    ratingMedium: r.ratings.medium,
    ratingStory: r.ratings.story,
    ratingTone: r.ratings.tone,
    ratingEnjoyability: r.ratings.enjoyability,
    ratingEffect: r.ratings.effect,
    notionImageUrl: r.imageUrl,
    notionMediaUrl: r.mediaUrl,
  };
}

export function importRows(db: Db, rows: LogRow[], opts: { dryRun?: boolean } = {}): ImportReport {
  const report: ImportReport = { inserted: 0, updated: 0, unchanged: 0, skipped: [], duplicates: [], insertedIds: [], changes: [] };
  const seen = new Set<string>();
  const run = () => {
    for (const r of rows) {
      const key = `${r.type}\u0000${r.title}`;
      if (seen.has(key)) report.duplicates.push(`${r.title} (${r.type})`);
      seen.add(key);

      const existing =
        (r.notionId ? db.select().from(media).where(eq(media.notionId, r.notionId)).get() : undefined) ??
        db.select().from(media).where(and(eq(media.title, r.title), eq(media.type, r.type))).get();

      const fields = notionFields(r);
      if (!existing) {
        if (!opts.dryRun) report.insertedIds.push(db.insert(media).values(fields).returning({ id: media.id }).get().id);
        report.inserted++;
        continue;
      }
      // Keep an id we already know if the file has none.
      if (!fields.notionId) fields.notionId = existing.notionId;
      const changedFields = (Object.keys(fields) as (keyof typeof fields)[]).filter((k) => (fields[k] ?? null) !== (existing[k] ?? null));
      if (changedFields.length === 0) { report.unchanged++; continue; }
      if (!opts.dryRun) {
        db.update(media).set({ ...fields, updatedAt: sql`(datetime('now'))` }).where(eq(media.id, existing.id)).run();
      }
      report.updated++;
      report.changes.push({ id: existing.id, fields: changedFields });
    }
  };
  if (opts.dryRun) run();
  else db.transaction(run);
  return report;
}

export function importCsv(db: Db, text: string, opts: { dryRun?: boolean } = {}): ImportReport {
  const { rows, skipped } = rowsFromCsv(text);
  const report = importRows(db, rows, opts);
  report.skipped.push(...skipped);
  return report;
}

/**
 * Rows read through the Notion API (the worker's sync). Unknown types are skipped
 * rather than failing the batch. When the batch is complete, entries whose Notion
 * row stopped coming back are marked (never deleted; /review lists them), and
 * returning ones are cleared.
 */
export function importNotionRows(db: Db, raw: { notionId: string | null; title: string; type: string; creator: string | null; loggedDate: string | null; ratings: LogRow['ratings']; imageUrl: string | null; mediaUrl: string | null }[], opts: { complete?: boolean } = {}): ImportReport & { missing: number } {
  const rows: LogRow[] = [];
  const skipped: ImportReport['skipped'] = [];
  raw.forEach((r, i) => {
    if (!(MEDIA_TYPES as readonly string[]).includes(r.type)) return skipped.push({ line: i + 1, reason: `unknown type "${r.type}" for "${r.title}"` });
    rows.push({ ...r, type: r.type as MediaType, notionId: r.notionId ? r.notionId.replace(/-/g, '').toLowerCase() : null });
  });
  const report = importRows(db, rows);
  report.skipped.push(...skipped);
  let missing = 0;
  if (opts.complete) {
    const seen = new Set(rows.map((r) => r.notionId).filter((x): x is string => !!x));
    db.transaction((tx) => {
      for (const m of tx.select({ id: media.id, notionId: media.notionId, missingSince: media.notionMissingSince }).from(media).all()) {
        if (!m.notionId) continue;
        if (seen.has(m.notionId)) {
          if (m.missingSince) tx.update(media).set({ notionMissingSince: null }).where(eq(media.id, m.id)).run();
        } else {
          missing++;
          if (!m.missingSince) tx.update(media).set({ notionMissingSince: sql`(datetime('now'))` }).where(eq(media.id, m.id)).run();
        }
      }
    });
  }
  return { ...report, missing };
}
