import { sql } from 'drizzle-orm';
import type { Db } from '../db/open';

export interface MediaHit { id: number; title: string; creator: string | null; type: string }

/** Turn free text into an FTS5 query: each word quoted, the last one as a prefix. */
export function ftsQuery(q: string): string | null {
  const words = q.replace(/["*]/g, ' ').split(/\s+/).filter(Boolean);
  if (words.length === 0) return null;
  return words.map((w, i) => (i === words.length - 1 ? `"${w}"*` : `"${w}"`)).join(' ');
}

export function searchMedia(db: Db, q: string, limit = 50): MediaHit[] {
  const match = ftsQuery(q);
  if (!match) return [];
  return db.all<MediaHit>(sql`
    SELECT m.id, m.title, m.creator, m.type
    FROM media_fts f JOIN media m ON m.id = f.rowid
    WHERE media_fts MATCH ${match}
    ORDER BY rank, m.title
    LIMIT ${limit}`);
}
