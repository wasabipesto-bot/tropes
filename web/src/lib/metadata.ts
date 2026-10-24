/**
 * Writing a lookup's result onto a media row (plan Phase 4). One function commits
 * a match (identity, details, links, genres, poster, extract); the rest are the
 * owner's corrections: pin a runner-up, say there is no match, hide a link.
 */
import { existsSync, mkdirSync, renameSync, unlinkSync } from 'node:fs';
import { dirname } from 'node:path';
import { and, eq, sql } from 'drizzle-orm';
import type { Db } from '../db/open';
import { media, mediaGenre, mediaLink, type Media } from '../db/schema';
import { POSTER_SIZES, posterPath } from './files';

export interface Candidate {
  qid: string | null;
  label: string;
  description: string;
  year: number | null;
  creator: string | null;
  kinds: string[];
  ids: Record<string, string>;
  wikipedia: string | null;
  score: number;
  reasons: string[];
  source: string;
}

export interface LinkIn { url: string; score?: string | null; score_value?: number | null }

export interface MatchPayload {
  status: 'confident' | 'check' | 'not_found';
  chosen: Candidate | null;
  candidates: Candidate[];
  details: Record<string, unknown>;
  links: Record<string, LinkIn>;
  genres: string[];
  ids: Record<string, string>;
  extract: string | null;
  /** The poster the worker uploaded to the pending directory, and where it came from. */
  poster: { source: string } | null;
  /** Other poster URLs the sites offered, kept in details.posters for the update flow's picker. */
  posters?: string[];
  notes: string[];
}

const now = () => sql`(datetime('now'))`;

/** Pin the chosen identity and store everything the lookup found. */
export function commitMatch(db: Db, mediaId: number, p: MatchPayload): void {
  if (!p.chosen) return;
  db.transaction((tx) => {
    const m = tx.select().from(media).where(eq(media.id, mediaId)).get();
    if (!m) return;
    tx.update(media)
      .set({
        identity: 'pinned',
        wikidataId: p.chosen!.qid,
        externalIds: JSON.stringify({ ...p.chosen!.ids, ...p.ids }),
        details: JSON.stringify({ ...(p.details ?? {}), ...(p.posters?.length ? { posters: p.posters.slice(0, 12) } : {}) }),
        identityCandidates: JSON.stringify(p.candidates.filter((c) => c.qid !== p.chosen!.qid || c.label !== p.chosen!.label).slice(0, 5)),
        wikiExtract: p.extract ?? m.wikiExtract,
        metadataAt: now(),
        reviewNote: null,
        updatedAt: now(),
      })
      .where(eq(media.id, mediaId))
      .run();
    replaceLinks(tx as unknown as Db, mediaId, p.links);
    if (!m.genresEdited) {
      tx.delete(mediaGenre).where(eq(mediaGenre.mediaId, mediaId)).run();
      for (const g of new Set(p.genres ?? [])) tx.insert(mediaGenre).values({ mediaId, genre: g }).run();
    }
    if (p.poster) placePoster(tx as unknown as Db, mediaId, p.poster.source);
  });
}

/** Lookup links are replaced wholesale; the owner's own links and hide flags survive. */
function replaceLinks(tx: Db, mediaId: number, links: Record<string, LinkIn>): void {
  const old = tx.select().from(mediaLink).where(eq(mediaLink.mediaId, mediaId)).all();
  tx.delete(mediaLink).where(and(eq(mediaLink.mediaId, mediaId), eq(mediaLink.origin, 'lookup'))).run();
  for (const [site, l] of Object.entries(links)) {
    if (old.some((o) => o.site === site && o.origin !== 'lookup')) continue;
    const hidden = old.find((o) => o.site === site)?.hidden ?? false;
    tx.insert(mediaLink).values({ mediaId, site, url: l.url, score: l.score ?? null, scoreValue: l.score_value ?? null, origin: 'lookup', hidden, fetchedAt: now() }).run();
  }
}

/** Move the pending poster files into place and record where they came from. */
export function placePoster(tx: Db, mediaId: number, source: string): void {
  let moved = false;
  for (const size of POSTER_SIZES) {
    const from = posterPath(mediaId, size, true);
    if (!existsSync(from)) continue;
    const to = posterPath(mediaId, size);
    mkdirSync(dirname(to), { recursive: true });
    renameSync(from, to);
    moved = true;
  }
  if (moved) tx.update(media).set({ posterPath: String(mediaId), posterSource: source }).where(eq(media.id, mediaId)).run();
}

export function discardPendingPoster(mediaId: number): void {
  for (const size of POSTER_SIZES) {
    const p = posterPath(mediaId, size, true);
    if (existsSync(p)) unlinkSync(p);
  }
}

/** The owner says none of the candidates is this work. Lookup data is cleared; the owner's links stay. */
export function markNoMatch(db: Db, mediaId: number, candidates: Candidate[] = []): void {
  db.transaction((tx) => {
    tx.update(media)
      .set({ identity: 'none', wikidataId: null, externalIds: '{}', details: '{}', identityCandidates: JSON.stringify(candidates.slice(0, 5)), metadataAt: now(), reviewNote: null, updatedAt: now() })
      .where(eq(media.id, mediaId))
      .run();
    tx.delete(mediaLink).where(and(eq(mediaLink.mediaId, mediaId), eq(mediaLink.origin, 'lookup'))).run();
    const m = tx.select().from(media).where(eq(media.id, mediaId)).get();
    if (m && !m.genresEdited) tx.delete(mediaGenre).where(eq(mediaGenre.mediaId, mediaId)).run();
  });
}

/** Pin a runner-up (or a candidate the owner supplied). Details are fetched by the refresh the caller queues. */
export function pinCandidate(db: Db, mediaId: number, c: Candidate, others: Candidate[]): void {
  db.transaction((tx) => {
    tx.update(media)
      .set({ identity: 'pinned', wikidataId: c.qid, externalIds: JSON.stringify(c.ids), details: '{}', identityCandidates: JSON.stringify(others.filter((o) => o !== c).slice(0, 5)), reviewNote: null, updatedAt: now() })
      .where(eq(media.id, mediaId))
      .run();
    tx.delete(mediaLink).where(and(eq(mediaLink.mediaId, mediaId), eq(mediaLink.origin, 'lookup'))).run();
  });
}

/** Mark an unsure or failed lookup on the row itself so /review can list it. */
export function recordUnresolved(db: Db, mediaId: number, p: MatchPayload): void {
  db.update(media)
    .set({ identity: p.status === 'check' ? 'check' : 'not_found', identityCandidates: JSON.stringify(p.candidates.slice(0, 5)), wikiExtract: p.extract ?? undefined, updatedAt: now() })
    .where(eq(media.id, mediaId))
    .run();
}

export function parseDetails(m: Pick<Media, 'details'>): Record<string, unknown> {
  try { return JSON.parse(m.details || '{}'); } catch { return {}; }
}
export function parseIds(m: Pick<Media, 'externalIds'>): Record<string, string> {
  try { return JSON.parse(m.externalIds || '{}'); } catch { return {}; }
}
export function parseCandidates(m: Pick<Media, 'identityCandidates'>): Candidate[] {
  try { return JSON.parse(m.identityCandidates || '[]'); } catch { return []; }
}
