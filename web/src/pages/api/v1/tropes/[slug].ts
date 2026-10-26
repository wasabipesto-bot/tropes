import type { APIRoute } from 'astro';
import { db } from '../../../../db';
import { apiJson, instanceJson } from '../../../../lib/api';
import { instancesForTrope, notableFor, tropeByAliasSlug, tropeBySlug } from '../../../../lib/queries';

/** Public read API: one trope with every instance and its evidence. Old slugs resolve like the page does. */
export const GET: APIRoute = ({ params }) => {
  const t = tropeBySlug(db, params.slug ?? '') ?? tropeByAliasSlug(db, params.slug ?? '');
  if (!t) return apiJson({ error: 'no such trope' }, 404);
  const items = instancesForTrope(db, t.id);
  return apiJson({
    id: t.id, name: t.name, slug: t.slug, description: t.description, visual: t.visual, url: `/tropes/${t.slug}`,
    notable: notableFor(db, t.id, items).map((v) => v.inst.id),
    instances: items.map(instanceJson),
  });
};
