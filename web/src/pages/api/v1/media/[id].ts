import type { APIRoute } from 'astro';
import { and, eq } from 'drizzle-orm';
import { db } from '../../../../db';
import { dossier, media, mediaGenre, mediaLink } from '../../../../db/schema';
import { apiJson, instanceJson } from '../../../../lib/api';
import { typeLabel } from '../../../../lib/media';
import { instancesForMedia, seriesForMedia } from '../../../../lib/queries';

/** Public read API: one work with its links, genres, instances and dossier. */
export const GET: APIRoute = ({ params }) => {
  const id = Number(params.id);
  const m = Number.isInteger(id) ? db.select().from(media).where(eq(media.id, id)).get() : undefined;
  if (!m) return apiJson({ error: 'no such work' }, 404);
  const d = db.select().from(dossier).where(and(eq(dossier.subjectKind, 'media'), eq(dossier.subjectId, m.id))).get();
  return apiJson({
    id: m.id, title: m.title, type: m.type, label: typeLabel(m), creator: m.creator, logged: m.loggedDate, description: m.description,
    genres: db.select().from(mediaGenre).where(eq(mediaGenre.mediaId, m.id)).all().map((g) => g.genre),
    links: db.select().from(mediaLink).where(eq(mediaLink.mediaId, m.id)).all().filter((l) => !l.hidden).map((l) => ({ site: l.site, url: l.url })),
    series: seriesForMedia(db, m.id).map((s) => ({ id: s.id, name: s.name, slug: s.slug, url: `/series/${s.slug}` })),
    wikidata: m.wikidataId, poster: m.posterPath ? `/posters/${m.id}-300.webp` : null, url: `/media/${m.id}`,
    instances: instancesForMedia(db, m.id).map(instanceJson),
    dossier: d ? { builtAt: d.builtAt, depth: d.depth, body: JSON.parse(d.body), url: `/media/${m.id}/dossier` } : null,
  });
};
