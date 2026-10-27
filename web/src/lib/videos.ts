import { and, asc, eq } from 'drizzle-orm';
import type { Db } from '../db/open';
import { mediaVideo, type MediaVideo } from '../db/schema';

/** What a URL is and how to embed it: YouTube and Vimeo by id (click-to-play iframes), direct files as <video>. */
export function classify(url: string): { provider: MediaVideo['provider']; id: string | null } {
  const yt = /(?:youtube\.com\/(?:watch\?(?:.*&)?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{11})/.exec(url);
  if (yt) return { provider: 'youtube', id: yt[1] };
  const vm = /vimeo\.com\/(?:video\/)?(\d+)/.exec(url);
  if (vm) return { provider: 'vimeo', id: vm[1] };
  if (/animethemes\.moe\/.*\.webm(\?|$)/.test(url)) return { provider: 'animethemes', id: null };
  if (/\.(webm|mp4|m4v)(\?|$)/i.test(url)) return { provider: 'file', id: null };
  return { provider: 'other', id: null };
}

export function embedFor(v: Pick<MediaVideo, 'provider' | 'url'>): { kind: 'iframe'; src: string; poster: string | null } | { kind: 'video'; src: string } | { kind: 'link' } {
  const c = classify(v.url);
  if (c.provider === 'youtube' && c.id) return { kind: 'iframe', src: `https://www.youtube-nocookie.com/embed/${c.id}?autoplay=1&rel=0`, poster: `https://i.ytimg.com/vi/${c.id}/hqdefault.jpg` };
  if (c.provider === 'vimeo' && c.id) return { kind: 'iframe', src: `https://player.vimeo.com/video/${c.id}?autoplay=1&dnt=1`, poster: null };
  if (c.provider === 'animethemes' || c.provider === 'file') return { kind: 'video', src: v.url };
  return { kind: 'link' };
}

export const VIDEO_KIND_LABEL: Record<MediaVideo['kind'], string> = { opening: 'Opening', ending: 'Ending', titles: 'Title sequence', trailer: 'Trailer', edit: 'Edit', other: 'Video' };
const KIND_ORDER: MediaVideo['kind'][] = ['titles', 'opening', 'ending', 'edit', 'trailer', 'other'];

export function videosFor(db: Db, mediaId: number, owner: boolean): MediaVideo[] {
  const rows = db.select().from(mediaVideo).where(eq(mediaVideo.mediaId, mediaId)).orderBy(asc(mediaVideo.position), asc(mediaVideo.id)).all();
  return rows.filter((v) => owner || !v.hidden).sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind) || a.position - b.position || a.id - b.id);
}

/** Worker and owner rows land here: one row per work and URL; an owner's row is never rewritten by a worker, hidden stays hidden. */
export function upsertVideo(db: Db, v: { mediaId: number; kind: MediaVideo['kind']; url: string; label?: string; origin: MediaVideo['origin']; sourceUrl?: string | null; position?: number }): 'added' | 'kept' | 'updated' {
  const provider = classify(v.url).provider;
  const existing = db.select().from(mediaVideo).where(and(eq(mediaVideo.mediaId, v.mediaId), eq(mediaVideo.url, v.url))).get();
  if (!existing) {
    db.insert(mediaVideo).values({ mediaId: v.mediaId, kind: v.kind, provider, url: v.url, label: v.label ?? '', origin: v.origin, sourceUrl: v.sourceUrl ?? null, position: v.position ?? 0 }).run();
    return 'added';
  }
  if (existing.origin === 'owner' && v.origin !== 'owner') return 'kept';
  db.update(mediaVideo).set({ kind: v.kind, label: v.label ?? existing.label, sourceUrl: v.sourceUrl ?? existing.sourceUrl, position: v.position ?? existing.position }).where(eq(mediaVideo.id, existing.id)).run();
  return 'updated';
}
