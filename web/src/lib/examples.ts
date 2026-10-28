import { media, series } from '../db/schema';
import type { Db } from '../db/open';
import type { SubjectKind } from '../db/schema';

/**
 * Typed titles that should still find the work: "Cyberpunk Edgerunners", "the empire strikes back (Luke)",
 * "Ocean's 11". A bracketed note at the end is the owner's note about the example, not part of the title.
 */
export function parseExample(raw: string): { title: string; note: string } {
  const m = /^(.*?)\s*\(([^()]{1,80})\)\s*$/.exec(raw.trim());
  if (m && !/^\d{4}$/.test(m[2])) return { title: m[1].trim(), note: m[2].trim() };
  return { title: raw.trim(), note: '' };
}

/** Case, accents, punctuation and "&" folded; what is left is letters, digits and single spaces. */
export function normTitle(s: string): string {
  return s
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[’'`]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

/** Levenshtein distance, early-out above `max`. */
export function editDistance(a: string, b: string, max = 2): number {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let rowMin = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      rowMin = Math.min(rowMin, cur[j]);
    }
    if (rowMin > max) return max + 1;
    prev = cur;
  }
  return prev[b.length];
}

export interface Match { kind: SubjectKind; id: number; title: string; how: 'exact' | 'loose' | 'fuzzy' }

/**
 * The work or series a typed title means: exact, then folded, then without the part after a colon on either
 * side, then within two typos (one for short titles). Null when nothing fits or two fit equally.
 */
export function matchSubject(db: Db, typed: string): Match | null {
  const t = typed.trim();
  if (!t) return null;
  const rows: { kind: SubjectKind; id: number; title: string }[] = [
    ...db.select({ id: series.id, title: series.name }).from(series).all().map((r) => ({ kind: 'series' as const, ...r })),
    ...db.select({ id: media.id, title: media.title }).from(media).all().map((r) => ({ kind: 'media' as const, ...r })),
  ];
  const exact = rows.filter((r) => r.title === t);
  if (exact.length === 1) return { ...exact[0], how: 'exact' };
  const n = normTitle(t);
  if (!n) return null;
  const loose = rows.filter((r) => normTitle(r.title) === n);
  if (loose.length === 1) return { ...loose[0], how: 'loose' };
  if (loose.length > 1) return null;
  // Subtitle-insensitive, either side of the colon, for titles of at least two words ("Cyberpunk" alone stays ambiguous).
  const head = (s: string) => normTitle(s.split(':')[0]);
  const tail = (s: string) => normTitle(s.split(':').slice(1).join(':'));
  if (n.split(' ').length >= 2) {
    const byPart = rows.filter((r) => head(r.title) === n || tail(r.title) === n || normTitle(r.title) === head(t) || normTitle(r.title) === tail(t));
    if (byPart.length === 1) return { ...byPart[0], how: 'loose' };
    if (byPart.length > 1) return null;
  }
  const max = n.length < 8 ? 1 : 2;
  const scored = rows.map((r) => ({ r, d: editDistance(normTitle(r.title), n, max) })).filter((x) => x.d <= max).sort((a, b) => a.d - b.d);
  if (scored.length === 0) return null;
  if (scored.length > 1 && scored[1].d === scored[0].d) return null;
  return { ...scored[0].r, how: 'fuzzy' };
}
