import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { MediaType } from '../db/schema';

export type GenreKind = 'story' | 'game' | 'music' | 'podcast';
export interface GenreEntry { name: string; kind: GenreKind; sub: string[] }
export interface GenreVocabulary { genres: GenreEntry[] }

let cached: GenreVocabulary | null = null;

/** web/seed/genres.json, read once. Two levels: a subgenre implies its parent. */
export function genreVocabulary(): GenreVocabulary {
  if (!cached) {
    const raw = JSON.parse(readFileSync(process.env.GENRES_FILE ?? resolve(process.cwd(), 'seed/genres.json'), 'utf8'));
    cached = { genres: raw.genres };
  }
  return cached;
}

/** Which vocabulary kinds apply to a media type. */
export function kindsFor(type: MediaType): GenreKind[] {
  if (type === 'Album') return ['music'];
  if (type === 'Game') return ['story', 'game'];
  if (type === 'Podcast') return ['story', 'podcast'];
  return ['story'];
}

/** genre → parent genre (top-level entries map to themselves). */
export function parentMap(v = genreVocabulary()): Map<string, string> {
  const out = new Map<string, string>();
  for (const g of v.genres) {
    out.set(g.name, g.name);
    for (const s of g.sub) out.set(s, g.name);
  }
  return out;
}

export function isGenre(name: string, v = genreVocabulary()): boolean {
  return parentMap(v).has(name);
}
