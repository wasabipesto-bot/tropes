import { dirname, join, resolve } from 'node:path';

/** Data directory: next to the database (web/data in dev, /app/data in the container). */
export function dataDir(): string {
  return dirname(resolve(process.env.DATABASE_PATH ?? './data/tropes.db'));
}

export const POSTER_SIZES = [900, 300, 50] as const;
export type PosterSize = (typeof POSTER_SIZES)[number];

/** Final poster files live in data/posters; uploads for an uncommitted lookup wait in data/posters/pending. */
export function posterPath(mediaId: number, size: PosterSize, pending = false): string {
  return join(dataDir(), 'posters', pending ? 'pending' : '', `${mediaId}-${size}.webp`);
}

/** Text the media worker extracted for a local source (subtitles, a book), one file per source row. */
export function textPath(sourceId: number): string {
  return join(dataDir(), 'texts', `${sourceId}.txt`);
}
