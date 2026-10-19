import { and, asc, eq, inArray, sql } from 'drizzle-orm';
import type { Db } from '../db/open';
import {
  evidence, instance, media, notable, series, seriesMember, trope,
  type Evidence, type Instance, type Media, type Prominence, type Series, type SubjectKind, type Trope,
} from '../db/schema';
import { typeLabel } from './media';

export const PROMINENCE_LABEL: Record<Prominence, string> = { core: 'Core theme', recurring: 'Recurring', brief: 'Brief' };
export const PROMINENCE_ORDER: Prominence[] = ['core', 'recurring', 'brief'];

export interface SubjectRef {
  kind: SubjectKind;
  id: number;
  title: string;
  href: string;
  /** Quiet label next to the title: "book", "TV", "book series". */
  label: string;
}

export interface InstanceView {
  inst: Instance;
  trope: Trope;
  subject: SubjectRef;
  evidence: Evidence[];
  notable: boolean;
  /** Set when a media page shows an instance that belongs to a series the work is part of. */
  viaSeries: Series | null;
}

export function tropeBySlug(db: Db, slug: string): Trope | undefined {
  return db.select().from(trope).where(eq(trope.slug, slug)).get();
}

export function seriesBySlug(db: Db, slug: string): Series | undefined {
  return db.select().from(series).where(eq(series.slug, slug)).get();
}

export function allTropes(db: Db): Trope[] {
  return db.select().from(trope).orderBy(asc(trope.name)).all();
}

/** Resolve [[Trope name]] links, case-insensitively. */
export function tropeHrefResolver(db: Db): (name: string) => string | null {
  const bySlug = new Map(allTropes(db).map((t) => [t.name.toLowerCase(), `/tropes/${t.slug}`]));
  return (name) => bySlug.get(name.trim().toLowerCase()) ?? null;
}

export function seriesMembers(db: Db, seriesId: number): Media[] {
  return db
    .select({ m: media })
    .from(seriesMember)
    .innerJoin(media, eq(media.id, seriesMember.mediaId))
    .where(eq(seriesMember.seriesId, seriesId))
    .orderBy(asc(seriesMember.position), asc(media.loggedDate))
    .all()
    .map((r) => r.m);
}

export function seriesForMedia(db: Db, mediaId: number): Series[] {
  return db
    .select({ s: series })
    .from(seriesMember)
    .innerJoin(series, eq(series.id, seriesMember.seriesId))
    .where(eq(seriesMember.mediaId, mediaId))
    .all()
    .map((r) => r.s);
}

function seriesLabel(db: Db, s: Series): string {
  const types = new Set(seriesMembers(db, s.id).map((m) => typeLabel(m)));
  return types.size === 1 ? `${[...types][0]} series` : 'series';
}

export function subjectRef(db: Db, kind: SubjectKind, id: number): SubjectRef | undefined {
  if (kind === 'media') {
    const m = db.select().from(media).where(eq(media.id, id)).get();
    return m && { kind, id, title: m.title, href: `/media/${m.id}`, label: typeLabel(m) };
  }
  const s = db.select().from(series).where(eq(series.id, id)).get();
  return s && { kind, id, title: s.name, href: `/series/${s.slug}`, label: seriesLabel(db, s) };
}

function evidenceByInstance(db: Db, ids: number[]): Map<number, Evidence[]> {
  const out = new Map<number, Evidence[]>();
  if (ids.length === 0) return out;
  for (const e of db.select().from(evidence).where(inArray(evidence.instanceId, ids)).orderBy(asc(evidence.position), asc(evidence.id)).all()) {
    out.set(e.instanceId, [...(out.get(e.instanceId) ?? []), e]);
  }
  return out;
}

function notableSet(db: Db, tropeIds: number[]): Set<number> {
  if (tropeIds.length === 0) return new Set();
  return new Set(db.select({ id: notable.instanceId }).from(notable).where(inArray(notable.tropeId, tropeIds)).all().map((r) => r.id));
}

function views(db: Db, rows: { inst: Instance; trope: Trope; viaSeries?: Series | null }[]): InstanceView[] {
  const ev = evidenceByInstance(db, rows.map((r) => r.inst.id));
  const pinned = notableSet(db, [...new Set(rows.map((r) => r.trope.id))]);
  const out: InstanceView[] = [];
  for (const r of rows) {
    const subject = subjectRef(db, r.inst.subjectKind, r.inst.subjectId);
    if (!subject) continue;
    out.push({ inst: r.inst, trope: r.trope, subject, evidence: ev.get(r.inst.id) ?? [], notable: pinned.has(r.inst.id), viaSeries: r.viaSeries ?? null });
  }
  return out;
}

export function instancesForTrope(db: Db, tropeId: number): InstanceView[] {
  const t = db.select().from(trope).where(eq(trope.id, tropeId)).get();
  if (!t) return [];
  const rows = db.select().from(instance).where(eq(instance.tropeId, tropeId)).orderBy(asc(instance.id)).all();
  return sortViews(views(db, rows.map((inst) => ({ inst, trope: t }))));
}

function forSubject(db: Db, kind: SubjectKind, id: number, viaSeries: Series | null): InstanceView[] {
  const rows = db
    .select({ inst: instance, trope })
    .from(instance)
    .innerJoin(trope, eq(trope.id, instance.tropeId))
    .where(and(eq(instance.subjectKind, kind), eq(instance.subjectId, id)))
    .orderBy(asc(instance.id))
    .all();
  return views(db, rows.map((r) => ({ ...r, viaSeries })));
}

/** A work's own instances plus those attached to any series it belongs to. */
export function instancesForMedia(db: Db, mediaId: number): InstanceView[] {
  const own = forSubject(db, 'media', mediaId, null);
  const inherited = seriesForMedia(db, mediaId).flatMap((s) => forSubject(db, 'series', s.id, s));
  return sortViews([...own, ...inherited]);
}

export function instancesForSeries(db: Db, seriesId: number): InstanceView[] {
  return sortViews(forSubject(db, 'series', seriesId, null));
}

/** Prominence order, then title. */
export function sortViews(list: InstanceView[]): InstanceView[] {
  const rank = (p: Prominence) => PROMINENCE_ORDER.indexOf(p);
  return list.slice().sort((a, b) => rank(a.inst.prominence) - rank(b.inst.prominence) || a.subject.title.localeCompare(b.subject.title) || a.trope.name.localeCompare(b.trope.name));
}

export interface Group { prominence: Prominence; label: string; items: InstanceView[] }

export function groupByProminence(list: InstanceView[]): Group[] {
  return PROMINENCE_ORDER.map((p) => ({ prominence: p, label: PROMINENCE_LABEL[p], items: list.filter((v) => v.inst.prominence === p) })).filter((g) => g.items.length > 0);
}

export function notableFor(db: Db, tropeId: number, all: InstanceView[]): InstanceView[] {
  const order = db.select().from(notable).where(eq(notable.tropeId, tropeId)).orderBy(asc(notable.position)).all();
  const byId = new Map(all.map((v) => [v.inst.id, v]));
  return order.map((n) => byId.get(n.instanceId)).filter((v): v is InstanceView => !!v);
}

export interface TropeIndexRow { trope: Trope; count: number; examples: string[] }

export function tropesIndex(db: Db): TropeIndexRow[] {
  return allTropes(db).map((t) => {
    const list = instancesForTrope(db, t.id);
    return { trope: t, count: list.length, examples: list.map((v) => v.subject.title) };
  });
}

/** Media titles and series names for the quick-add datalist. */
export function subjectTitles(db: Db): string[] {
  const titles = db.select({ t: media.title }).from(media).all().map((r) => r.t);
  const names = db.select({ n: series.name }).from(series).all().map((r) => r.n);
  return [...new Set([...titles, ...names])].sort((a, b) => a.localeCompare(b));
}

/** Find the subject a typed title refers to: a series by name first, then a media title (exact, then case-insensitive). */
export function resolveSubject(db: Db, title: string): { kind: SubjectKind; id: number } | undefined {
  const t = title.trim();
  if (!t) return undefined;
  const s = db.select().from(series).where(eq(series.name, t)).get();
  if (s) return { kind: 'series', id: s.id };
  const exact = db.select().from(media).where(eq(media.title, t)).get();
  if (exact) return { kind: 'media', id: exact.id };
  const loose = db.select().from(media).where(sql`lower(${media.title}) = lower(${t})`).get();
  return loose && { kind: 'media', id: loose.id };
}

export function resolveTrope(db: Db, name: string): Trope | undefined {
  const n = name.trim();
  if (!n) return undefined;
  return db.select().from(trope).where(sql`lower(${trope.name}) = lower(${n})`).get();
}

/** Instance counts per media id, with the core-theme ones first, for the library's tropes column. */
export function tropesByMedia(db: Db): Map<number, { name: string; slug: string; prominence: Prominence }[]> {
  const rows = db
    .select({ subjectId: instance.subjectId, subjectKind: instance.subjectKind, prominence: instance.prominence, name: trope.name, slug: trope.slug })
    .from(instance)
    .innerJoin(trope, eq(trope.id, instance.tropeId))
    .all();
  const members = db.select().from(seriesMember).all();
  const out = new Map<number, { name: string; slug: string; prominence: Prominence }[]>();
  const push = (mediaId: number, r: (typeof rows)[number]) => out.set(mediaId, [...(out.get(mediaId) ?? []), { name: r.name, slug: r.slug, prominence: r.prominence }]);
  for (const r of rows) {
    if (r.subjectKind === 'media') push(r.subjectId, r);
    else for (const m of members) if (m.seriesId === r.subjectId) push(m.mediaId, r);
  }
  const rank = (p: Prominence) => PROMINENCE_ORDER.indexOf(p);
  for (const [k, v] of out) out.set(k, v.sort((a, b) => rank(a.prominence) - rank(b.prominence) || a.name.localeCompare(b.name)));
  return out;
}
