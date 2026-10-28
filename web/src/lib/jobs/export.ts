import { eq } from 'drizzle-orm';
import type { Db } from '../../db/open';
import { dossier, instance, localSource, media, mediaGenre, mediaLink, mediaNote, mediaVideo, proposal, series, seriesMember, trope, tropeSeed } from '../../db/schema';
import { typeLabel } from '../media';

/** Everything the worker needs to scan: tropes, their seeds, and what is already attached or was rejected. */
export function exportTropes(db: Db) {
  const seeds = db.select().from(tropeSeed).all();
  const insts = db.select({ id: instance.id, tropeId: instance.tropeId, kind: instance.subjectKind, subjectId: instance.subjectId, who: instance.who, text: instance.text, prominence: instance.prominence, verified: instance.verified }).from(instance).all();
  const rejected = db.select({ tropeId: proposal.tropeId, kind: proposal.subjectKind, subjectId: proposal.subjectId }).from(proposal).where(eq(proposal.decision, 'rejected')).all();
  return db.select().from(trope).all().map((t) => ({
    id: t.id,
    name: t.name,
    slug: t.slug,
    description: t.description,
    visual: t.visual,
    seeds: seeds.filter((s) => s.tropeId === t.id).map((s) => ({ title: s.title, mediaId: s.mediaId })),
    instances: insts.filter((i) => i.tropeId === t.id).map(({ tropeId: _t, ...rest }) => rest),
    rejected: rejected.filter((r) => r.tropeId === t.id).map((r) => ({ kind: r.kind, id: r.subjectId })),
  }));
}

/** Every media item and series with the fields a dossier needs, plus what the worker already built. */
export function exportSubjects(db: Db) {
  const sources = db.select().from(localSource).all();
  const notes = db.select().from(mediaNote).all();
  const links = db.select({ mediaId: mediaLink.mediaId, site: mediaLink.site, url: mediaLink.url }).from(mediaLink).all();
  const videos = db.select({ mediaId: mediaVideo.mediaId, kind: mediaVideo.kind, url: mediaVideo.url, origin: mediaVideo.origin }).from(mediaVideo).all();
  const genres = db.select().from(mediaGenre).all();
  const built = db.select({ kind: dossier.subjectKind, id: dossier.subjectId, depth: dossier.depth, promptVersion: dossier.promptVersion, sourceHash: dossier.sourceHash, body: dossier.body, inputs: dossier.inputs }).from(dossier).all()
    .map(({ body, inputs, ...rest }) => ({
      ...rest,
      known: (() => { try { return JSON.parse(body).known ?? null; } catch { return null; } })() as string | null,
      visual: (() => { try { return Number(JSON.parse(inputs || '{}').visual ?? 0); } catch { return 0; } })(),
    }));
  const members = db.select().from(seriesMember).all();
  const dossierFor = (kind: 'media' | 'series', id: number) => built.find((b) => b.kind === kind && b.id === id) ?? null;
  const mediaRows = db.select().from(media).all().map((m) => ({
    kind: 'media' as const,
    id: m.id,
    title: m.title,
    type: m.type,
    label: typeLabel(m),
    creator: m.creator,
    year: m.loggedDate ? Number(m.loggedDate.slice(0, 4)) : null,
    description: m.description,
    aliases: m.aliases,
    knowledgeOnly: m.knowledgeOnly,
    links: links.filter((l) => l.mediaId === m.id).map(({ site, url }) => ({ site, url })),
    videos: videos.filter((v) => v.mediaId === m.id).map(({ kind, url, origin }) => ({ kind, url, origin })),
    genres: genres.filter((g) => g.mediaId === m.id).map((g) => g.genre),
    // Phase 4: what the lookup needs and what it already pinned.
    mediaUrl: m.notionMediaUrl,
    localRoot: m.localRoot,
    imageUrl: m.notionImageUrl,
    identity: m.identity,
    wikidataId: m.wikidataId,
    externalIds: JSON.parse(m.externalIds || '{}'),
    details: JSON.parse(m.details || '{}'),
    posterSource: m.posterSource,
    posterPath: m.posterPath,
    wikiExtract: m.wikiExtract,
    genresEdited: m.genresEdited,
    textSources: sources.filter((s) => s.mediaId === m.id && s.kind === 'text').map((s) => s.path),
    // Phase 5: what the media worker found and indexed for this work.
    localSources: sources.filter((s) => s.mediaId === m.id && s.kind !== 'text').map((s) => ({ id: s.id, kind: s.kind, path: s.path, label: s.label, meta: JSON.parse(s.meta || '{}'), indexedAt: s.indexedAt })),
    notes: notes.filter((n) => n.mediaId === m.id).map((n) => ({ source: n.source, url: n.url, text: n.text, label: n.label })),
    dossier: dossierFor('media', m.id),
  }));
  const seriesRows = db.select().from(series).all().map((s) => ({
    kind: 'series' as const,
    id: s.id,
    name: s.name,
    description: s.description,
    members: members.filter((m) => m.seriesId === s.id).sort((a, b) => a.position - b.position).map((m) => m.mediaId),
    dossier: dossierFor('series', s.id),
  }));
  return { media: mediaRows, series: seriesRows };
}
