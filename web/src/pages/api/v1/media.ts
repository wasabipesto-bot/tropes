import type { APIRoute } from 'astro';
import { db } from '../../../db';
import { media, mediaGenre } from '../../../db/schema';
import { apiJson } from '../../../lib/api';
import { typeLabel } from '../../../lib/media';

/** Public read API: the library. */
export const GET: APIRoute = () => {
  const genres = db.select().from(mediaGenre).all();
  return apiJson({
    media: db.select().from(media).all().map((m) => ({
      id: m.id, title: m.title, type: m.type, label: typeLabel(m), creator: m.creator, logged: m.loggedDate, description: m.description,
      genres: genres.filter((g) => g.mediaId === m.id).map((g) => g.genre), wikidata: m.wikidataId, poster: m.posterPath ? `/posters/${m.id}-300.webp` : null, url: `/media/${m.id}`,
    })),
  });
};
