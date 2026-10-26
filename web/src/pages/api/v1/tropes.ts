import type { APIRoute } from 'astro';
import { db } from '../../../db';
import { apiJson } from '../../../lib/api';
import { allTropes, instancesForTrope } from '../../../lib/queries';

/** Public read API: every trope with its instance count. */
export const GET: APIRoute = () =>
  apiJson({
    tropes: allTropes(db).map((t) => ({ id: t.id, name: t.name, slug: t.slug, description: t.description, visual: t.visual, instances: instancesForTrope(db, t.id).length, url: `/tropes/${t.slug}` })),
  });
