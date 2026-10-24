import { eq, sql } from 'drizzle-orm';
import type { Db } from '../db/open';
import { instance, media, proposal, series, trope, tropeAlias } from '../db/schema';
import { slugify } from './slug';

/**
 * Rename a trope in one transaction (plan T15): the name and slug change, [[Old name]] becomes
 * [[New name]] wherever it is written (descriptions, instance text, pending proposals), and the old
 * name and slug are kept as an alias so old URLs redirect and old links still resolve. Evidence
 * quotes are never rewritten.
 */
export function renameTrope(db: Db, tropeId: number, newName: string): { slug: string; rewritten: number } | { error: string } {
  const t = db.select().from(trope).where(eq(trope.id, tropeId)).get();
  if (!t) return { error: 'No such trope.' };
  const slug = slugify(newName);
  if (!slug) return { error: 'The name needs at least one letter or digit.' };
  if (newName === t.name) return { slug, rewritten: 0 };
  const clash = db.select().from(trope).where(sql`lower(${trope.name}) = lower(${newName}) or ${trope.slug} = ${slug}`).get();
  if (clash && clash.id !== t.id) return { error: `“${clash.name}” already uses that name.` };
  const aliasClash = db.select().from(tropeAlias).where(eq(tropeAlias.slug, slug)).get();
  if (aliasClash && aliasClash.tropeId !== t.id) return { error: 'Another trope used to have that name; pick a different one.' };

  const link = new RegExp(`\\[\\[\\s*${escapeRegExp(t.name)}\\s*\\]\\]`, 'gi');
  const replacement = `[[${newName}]]`;
  let rewritten = 0;
  const rewrite = (text: string | null) => {
    if (!text || !link.test(text)) return null;
    rewritten++;
    return text.replace(link, replacement);
  };
  db.transaction((tx) => {
    tx.delete(tropeAlias).where(eq(tropeAlias.slug, slug)).run(); // the trope takes its own old name back
    if (slug !== t.slug) tx.insert(tropeAlias).values({ tropeId: t.id, name: t.name, slug: t.slug }).run();
    tx.update(trope).set({ name: newName, slug, updatedAt: sql`(datetime('now'))` }).where(eq(trope.id, t.id)).run();
    for (const row of tx.select({ id: trope.id, description: trope.description }).from(trope).all()) {
      const next = rewrite(row.description);
      if (next !== null) tx.update(trope).set({ description: next }).where(eq(trope.id, row.id)).run();
    }
    for (const row of tx.select({ id: instance.id, text: instance.text }).from(instance).all()) {
      const next = rewrite(row.text);
      if (next !== null) tx.update(instance).set({ text: next }).where(eq(instance.id, row.id)).run();
    }
    for (const row of tx.select({ id: media.id, description: media.description }).from(media).all()) {
      const next = rewrite(row.description);
      if (next !== null) tx.update(media).set({ description: next }).where(eq(media.id, row.id)).run();
    }
    for (const row of tx.select({ id: series.id, description: series.description }).from(series).all()) {
      const next = rewrite(row.description);
      if (next !== null) tx.update(series).set({ description: next }).where(eq(series.id, row.id)).run();
    }
    for (const row of tx.select({ id: proposal.id, text: proposal.text }).from(proposal).where(eq(proposal.decision, 'pending')).all()) {
      const next = rewrite(row.text);
      if (next !== null) tx.update(proposal).set({ text: next }).where(eq(proposal.id, row.id)).run();
    }
  });
  return { slug, rewritten };
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
