import { ActionError, defineAction } from 'astro:actions';
import { getSecret } from 'astro:env/server';
import { z } from 'astro/zod';
import { and, eq, sql } from 'drizzle-orm';
import type { ActionAPIContext } from 'astro:actions';
import { db } from '../db';
import { PROMINENCES, dossier, evidence, instance, job, media, mediaGenre, mediaLink, notable, proposal, series, trope, tropeAlias, tropeSeed } from '../db/schema';
import { cancelJob, createJob, jobById, parseJson } from '../lib/jobs/queue';
import { commitProposals } from '../lib/jobs/commit';
import { commitInput, commitMatchesInput } from '../lib/jobs/forms';
import { BACKFILL_BATCH, matchesFor, pinnedMediaIds, unresolvedMediaIds } from '../lib/jobs/matches';
import { commitMatch, markNoMatch, pinCandidate, type Candidate } from '../lib/metadata';
import { seedFromUrl } from '../lib/seeds';
import { isGenre } from '../lib/genres';
import { siteOf } from '../lib/media';
import { renameTrope } from '../lib/rename';
import { RateLimiter, SESSION_COOKIE, SESSION_DAYS, createSession, deleteSession } from '../lib/auth';
import { verifyPassword } from '../lib/password';
import { resolveSubject, resolveTrope } from '../lib/queries';
import { slugify } from '../lib/slug';

const loginLimiter = new RateLimiter(5, 60_000);
const now = () => sql`(datetime('now'))`;

function requireOwner(context: ActionAPIContext) {
  if (!context.locals.owner) throw new ActionError({ code: 'UNAUTHORIZED', message: 'Log in to edit.' });
}

/** Only same-site paths may be used as a post-action destination. */
const returnTo = z.string().regex(/^\/[^/\\]?[^\\]*$/).optional();
const id = z.coerce.number().int().positive();

export const server = {
  login: defineAction({
    accept: 'form',
    input: z.object({ password: z.string().min(1) }),
    handler: async ({ password }, context) => {
      const key = context.clientAddress ?? 'unknown';
      if (!loginLimiter.allow(key)) throw new ActionError({ code: 'TOO_MANY_REQUESTS', message: 'Too many attempts. Wait a minute.' });
      if (!verifyPassword(password, getSecret('OWNER_PASSWORD_HASH'))) throw new ActionError({ code: 'UNAUTHORIZED', message: 'That is not the password.' });
      const s = createSession(db, context.request.headers.get('user-agent'));
      context.cookies.set(SESSION_COOKIE, s.id, { httpOnly: true, secure: context.url.protocol === 'https:', sameSite: 'lax', path: '/', maxAge: SESSION_DAYS * 86_400 });
      return { returnTo: '/tropes' };
    },
  }),

  logout: defineAction({
    accept: 'form',
    input: z.object({ returnTo }),
    handler: async (input, context) => {
      deleteSession(db, context.cookies.get(SESSION_COOKIE)?.value);
      context.cookies.delete(SESSION_COOKIE, { path: '/' });
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  updateTropeDescription: defineAction({
    accept: 'form',
    input: z.object({ tropeId: id, description: z.string(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.update(trope).set({ description: input.description.trim(), updatedAt: now() }).where(eq(trope.id, input.tropeId)).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  updateMediaDescription: defineAction({
    accept: 'form',
    input: z.object({ mediaId: id, description: z.string(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.update(media).set({ description: input.description.trim() || null, updatedAt: now() }).where(eq(media.id, input.mediaId)).run();
      return { returnTo: input.returnTo ?? `/media/${input.mediaId}` };
    },
  }),

  updateSeriesDescription: defineAction({
    accept: 'form',
    input: z.object({ seriesId: id, description: z.string(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.update(series).set({ description: input.description.trim() || null, updatedAt: now() }).where(eq(series.id, input.seriesId)).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  createTrope: defineAction({
    accept: 'form',
    input: z.object({ name: z.string().trim().min(1), description: z.string(), examples: z.string().optional() }),
    handler: async (input, context) => {
      requireOwner(context);
      const slug = slugify(input.name);
      if (!slug) throw new ActionError({ code: 'BAD_REQUEST', message: 'The name needs at least one letter or digit.' });
      if (db.select().from(trope).where(eq(trope.slug, slug)).get()) throw new ActionError({ code: 'CONFLICT', message: 'A trope with that name already exists.' });
      const created = db.insert(trope).values({ name: input.name, slug, description: input.description.trim() }).returning().get();
      for (const line of (input.examples ?? '').split('\n').map((l) => l.trim()).filter(Boolean)) {
        const subject = resolveSubject(db, line);
        db.insert(tropeSeed).values({ tropeId: created.id, title: line, mediaId: subject?.kind === 'media' ? subject.id : null }).run();
      }
      return { returnTo: `/tropes/${slug}` };
    },
  }),

  /** Manual association from a trope page: type a title, press Add. */
  addInstanceByTitle: defineAction({
    accept: 'form',
    input: z.object({ tropeId: id, title: z.string().trim().min(1), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const subject = resolveSubject(db, input.title);
      if (!subject) throw new ActionError({ code: 'NOT_FOUND', message: `Nothing in the library is called “${input.title}”.` });
      const t = db.select().from(trope).where(eq(trope.id, input.tropeId)).get();
      if (!t) throw new ActionError({ code: 'NOT_FOUND', message: 'No such trope.' });
      const created = db.insert(instance).values({ tropeId: t.id, subjectKind: subject.kind, subjectId: subject.id, verified: true, origin: 'manual' }).returning().get();
      return { returnTo: `/tropes/${t.slug}?edit=${created.id}&text=1` };
    },
  }),

  /** Manual association from a media or series page: type a trope name, press Add. */
  addInstanceByTrope: defineAction({
    accept: 'form',
    input: z.object({ subjectKind: z.enum(['media', 'series']), subjectId: id, tropeName: z.string().trim().min(1), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const t = resolveTrope(db, input.tropeName);
      if (!t) throw new ActionError({ code: 'NOT_FOUND', message: `There is no trope called “${input.tropeName}”.` });
      const created = db.insert(instance).values({ tropeId: t.id, subjectKind: input.subjectKind, subjectId: input.subjectId, verified: true, origin: 'manual' }).returning().get();
      const base = input.returnTo ?? '/tropes';
      return { returnTo: `${base}${base.includes('?') ? '&' : '?'}edit=${created.id}&text=1` };
    },
  }),

  setProminence: defineAction({
    accept: 'form',
    input: z.object({ instanceId: id, prominence: z.enum(PROMINENCES), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.update(instance).set({ prominence: input.prominence, updatedAt: now() }).where(eq(instance.id, input.instanceId)).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  toggleVerified: defineAction({
    accept: 'form',
    input: z.object({ instanceId: id, returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.update(instance).set({ verified: sql`NOT ${instance.verified}`, updatedAt: now() }).where(eq(instance.id, input.instanceId)).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  updateInstanceText: defineAction({
    accept: 'form',
    input: z.object({ instanceId: id, who: z.string(), text: z.string(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.update(instance).set({ who: input.who.trim(), text: input.text.trim(), updatedAt: now() }).where(eq(instance.id, input.instanceId)).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  removeInstance: defineAction({
    accept: 'form',
    input: z.object({ instanceId: id, returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.delete(instance).where(eq(instance.id, input.instanceId)).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  toggleNotable: defineAction({
    accept: 'form',
    input: z.object({ instanceId: id, returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const inst = db.select().from(instance).where(eq(instance.id, input.instanceId)).get();
      if (!inst) throw new ActionError({ code: 'NOT_FOUND', message: 'No such instance.' });
      const existing = db.select().from(notable).where(and(eq(notable.tropeId, inst.tropeId), eq(notable.instanceId, inst.id))).get();
      if (existing) {
        db.delete(notable).where(and(eq(notable.tropeId, inst.tropeId), eq(notable.instanceId, inst.id))).run();
      } else {
        const [{ n }] = db.select({ n: sql<number>`coalesce(max(${notable.position}), -1) + 1` }).from(notable).where(eq(notable.tropeId, inst.tropeId)).all();
        db.insert(notable).values({ tropeId: inst.tropeId, instanceId: inst.id, position: n }).run();
      }
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  addQuote: defineAction({
    accept: 'form',
    input: z.object({ instanceId: id, content: z.string().trim().min(1), locator: z.string().trim().optional(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const [{ n }] = db.select({ n: sql<number>`coalesce(max(${evidence.position}), -1) + 1` }).from(evidence).where(eq(evidence.instanceId, input.instanceId)).all();
      db.insert(evidence).values({ instanceId: input.instanceId, kind: 'quote', content: input.content, locator: input.locator ?? '', position: n }).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  removeEvidence: defineAction({
    accept: 'form',
    input: z.object({ evidenceId: id, returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.delete(evidence).where(eq(evidence.id, input.evidenceId)).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  /** Add-trope step 1: nothing is saved; the draft travels in the job. */
  startTropeScan: defineAction({
    accept: 'form',
    input: z.object({ name: z.string().trim().min(1), description: z.string(), examples: z.string().optional() }),
    handler: async (input, context) => {
      requireOwner(context);
      if (!slugify(input.name)) throw new ActionError({ code: 'BAD_REQUEST', message: 'The name needs at least one letter or digit.' });
      if (db.select().from(trope).where(eq(trope.slug, slugify(input.name))).get()) throw new ActionError({ code: 'CONFLICT', message: 'A trope with that name already exists. Recheck it from its page instead.' });
      const seeds = (input.examples ?? '').split('\n').map((l) => l.trim()).filter(Boolean);
      const j = createJob(db, 'scan_trope', { mode: 'add', draft: { name: input.name, description: input.description.trim(), seeds } });
      return { returnTo: `/add/trope?job=${j.id}` };
    },
  }),

  /** Recheck an existing trope: additions only. */
  startTropeRecheck: defineAction({
    accept: 'form',
    input: z.object({ tropeId: id }),
    handler: async (input, context) => {
      requireOwner(context);
      const t = db.select().from(trope).where(eq(trope.id, input.tropeId)).get();
      if (!t) throw new ActionError({ code: 'NOT_FOUND', message: 'No such trope.' });
      const j = createJob(db, 'scan_trope', { mode: 'recheck', tropeId: t.id });
      return { returnTo: `/recheck/trope/${t.slug}?job=${j.id}` };
    },
  }),

  /** Check one work or series against every trope (the update flow's tropes part). */
  startSubjectCheck: defineAction({
    accept: 'form',
    input: z.object({ subjectKind: z.enum(['media', 'series']), subjectId: id }),
    handler: async (input, context) => {
      requireOwner(context);
      const subject = { kind: input.subjectKind, id: input.subjectId };
      const j = createJob(db, 'check_subject', { mode: 'recheck', subject });
      const back = subject.kind === 'media' ? `/update/media/${subject.id}` : `/recheck/series/${subject.id}`;
      return { returnTo: `${back}?job=${j.id}` };
    },
  }),

  startDossierBuild: defineAction({
    accept: 'form',
    input: z.object({ onlyMissing: z.coerce.boolean().default(true), subjectKind: z.enum(['media', 'series']).optional(), subjectId: id.optional(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const one = input.subjectKind && input.subjectId ? [{ kind: input.subjectKind, id: input.subjectId }] : undefined;
      const j = createJob(db, 'build_dossiers', { onlyMissing: input.onlyMissing, ...(one ? { subjects: one } : {}) });
      return { returnTo: input.returnTo ? `${input.returnTo}?job=${j.id}` : `/jobs?job=${j.id}` };
    },
  }),

  discardJob: defineAction({
    accept: 'form',
    input: z.object({ jobId: id, returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      if (jobById(db, input.jobId)) cancelJob(db, input.jobId);
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  /** Edit one proposal's who/text before committing. */
  updateProposal: defineAction({
    accept: 'form',
    input: z.object({ proposalId: id, who: z.string(), text: z.string(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      db.update(proposal).set({ who: input.who.trim(), text: input.text.trim() }).where(eq(proposal.id, input.proposalId)).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  /** Hide or show a link in the links line; the owner's own links can be removed. */
  toggleLinkHidden: defineAction({
    accept: 'form',
    input: z.object({ linkId: id, remove: z.string().optional(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const l = db.select().from(mediaLink).where(eq(mediaLink.id, input.linkId)).get();
      if (!l) throw new ActionError({ code: 'NOT_FOUND', message: 'No such link.' });
      if (input.remove && l.origin === 'owner') db.delete(mediaLink).where(eq(mediaLink.id, l.id)).run();
      else db.update(mediaLink).set({ hidden: !l.hidden }).where(eq(mediaLink.id, l.id)).run();
      return { returnTo: input.returnTo ?? `/media/${l.mediaId}` };
    },
  }),

  /** Add a link by URL; the site is recognised from the host and replaces the lookup's link for that site. */
  addLink: defineAction({
    accept: 'form',
    input: z.object({ mediaId: id, url: z.url().trim(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const site = siteOf(input.url) ?? new URL(input.url).hostname.replace(/^www\./, '');
      db.transaction((tx) => {
        tx.delete(mediaLink).where(and(eq(mediaLink.mediaId, input.mediaId), eq(mediaLink.site, site))).run();
        tx.insert(mediaLink).values({ mediaId: input.mediaId, site, url: input.url, origin: 'owner' }).run();
      });
      return { returnTo: input.returnTo ?? `/media/${input.mediaId}` };
    },
  }),

  /** Replace an entry's genres with the checked vocabulary entries; from then on refreshes leave them alone. */
  updateGenres: defineAction({
    accept: 'form',
    input: z.object({ mediaId: id, genre: z.array(z.string()).optional(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const picked = [...new Set((input.genre ?? []).filter((g) => isGenre(g)))];
      db.transaction((tx) => {
        tx.delete(mediaGenre).where(eq(mediaGenre.mediaId, input.mediaId)).run();
        for (const g of picked) tx.insert(mediaGenre).values({ mediaId: input.mediaId, genre: g }).run();
        tx.update(media).set({ genresEdited: true, updatedAt: now() }).where(eq(media.id, input.mediaId)).run();
      });
      return { returnTo: input.returnTo ?? `/media/${input.mediaId}` };
    },
  }),

  /**
   * The update flow's one commit (plan T13): the identity choice (keep, a runner-up, none, or a pasted link),
   * the description, and the poster choice. A changed identity or poster queues a refresh to fetch it.
   */
  updateMedia: defineAction({
    accept: 'form',
    input: z.object({ mediaId: id, identity: z.string().default('keep'), seedUrl: z.string().trim().optional(), description: z.string().optional(), poster: z.string().optional(), posterUrl: z.string().trim().optional() }),
    handler: async (input, context) => {
      requireOwner(context);
      const m = db.select().from(media).where(eq(media.id, input.mediaId)).get();
      if (!m) throw new ActionError({ code: 'NOT_FOUND', message: 'No such entry.' });
      const candidates: Candidate[] = JSON.parse(m.identityCandidates || '[]');
      let refresh = false;
      let posterWanted: string | null = null;
      if (input.identity === 'none') {
        markNoMatch(db, m.id, candidates);
      } else if (input.identity === 'link') {
        const seed = input.seedUrl ? seedFromUrl(input.seedUrl) : null;
        if (!seed) throw new ActionError({ code: 'BAD_REQUEST', message: 'Paste an IMDb, Steam, Goodreads, TMDB, MyAnimeList, Open Library, MusicBrainz, Wikipedia or Wikidata link.' });
        const ids = { ...seed.ids, ...(seed.wikipedia ? { wikipedia: seed.wikipedia } : {}) };
        pinCandidate(db, m.id, { qid: seed.qid ?? null, label: m.title, description: '', year: null, creator: m.creator, kinds: [], ids, wikipedia: seed.wikipedia ?? null, score: 1, reasons: ['link from the owner'], source: 'owner' }, candidates);
        refresh = true;
      } else if (/^\d+$/.test(input.identity) && candidates[Number(input.identity)]) {
        pinCandidate(db, m.id, candidates[Number(input.identity)], candidates);
        refresh = true;
      }
      if (input.description !== undefined) {
        const text = input.description.trim();
        if (text !== (m.description ?? '')) db.update(media).set({ description: text || null, descriptionOrigin: text ? 'owner' : null, updatedAt: now() }).where(eq(media.id, m.id)).run();
        else if (text && m.descriptionOrigin === 'model' && input.identity === 'keep') db.update(media).set({ descriptionOrigin: 'owner' }).where(eq(media.id, m.id)).run();
      }
      if (!m.notionImageUrl) {
        if (input.poster === 'url' && input.posterUrl) posterWanted = input.posterUrl;
        else if (input.poster && /^https?:\/\//.test(input.poster) && input.poster !== m.posterSource) posterWanted = input.poster;
      }
      if (posterWanted || refresh) {
        const fresh = db.select().from(media).where(eq(media.id, m.id)).get()!;
        if (fresh.identity === 'pinned') createJob(db, 'lookup_media', { mediaIds: [m.id], refresh: true, auto: true, ...(posterWanted ? { poster: posterWanted } : {}) });
      }
      return { returnTo: `/media/${m.id}` };
    },
  }),

  /** Save the owner's edits to a dossier. Rebuilds overwrite them (plan D21, as decided). */
  updateDossier: defineAction({
    accept: 'form',
    input: z.object({ subjectKind: z.enum(['media', 'series']), subjectId: id, summary: z.string(), characters: z.string(), settings: z.string(), arcs: z.string(), motifs: z.string(), themes: z.string(), notable_scenes: z.string(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const d = db.select().from(dossier).where(and(eq(dossier.subjectKind, input.subjectKind), eq(dossier.subjectId, input.subjectId))).get();
      if (!d) throw new ActionError({ code: 'NOT_FOUND', message: 'No dossier yet.' });
      const body = JSON.parse(d.body);
      const lines = (s: string) => s.split('\n').map((l) => l.trim()).filter(Boolean);
      body.summary = input.summary.trim();
      body.characters = lines(input.characters).map((l) => { const [name, ...rest] = l.split(':'); return { name: name.trim(), role: rest.join(':').trim(), descriptors: [], relationships: [] }; });
      body.settings = lines(input.settings);
      body.arcs = lines(input.arcs).map((l) => ({ summary: l, locator: null }));
      body.motifs = lines(input.motifs);
      body.themes = lines(input.themes);
      body.notable_scenes = lines(input.notable_scenes).map((l) => ({ summary: l, locator: null }));
      db.update(dossier).set({ body: JSON.stringify(body) }).where(and(eq(dossier.subjectKind, input.subjectKind), eq(dossier.subjectId, input.subjectId))).run();
      return { returnTo: input.returnTo ?? '/tropes' };
    },
  }),

  /** Rename a trope: links are rewritten and the old name keeps working (plan T15). */
  renameTrope: defineAction({
    accept: 'form',
    input: z.object({ tropeId: id, name: z.string().trim().min(1) }),
    handler: async (input, context) => {
      requireOwner(context);
      const out = renameTrope(db, input.tropeId, input.name);
      if ('error' in out) throw new ActionError({ code: 'CONFLICT', message: out.error });
      return { returnTo: `/tropes/${out.slug}` };
    },
  }),

  /** Remove an entry that is gone from Notion (listed in /review); its instances and files go with it. */
  removeMedia: defineAction({
    accept: 'form',
    input: z.object({ mediaId: id }),
    handler: async (input, context) => {
      requireOwner(context);
      const m = db.select().from(media).where(eq(media.id, input.mediaId)).get();
      if (!m) throw new ActionError({ code: 'NOT_FOUND', message: 'No such entry.' });
      if (!m.notionMissingSince) throw new ActionError({ code: 'BAD_REQUEST', message: 'Only entries gone from Notion can be removed here.' });
      db.delete(media).where(eq(media.id, m.id)).run();
      return { returnTo: '/review' };
    },
  }),

  /** Phase 4: look up every entry without a pinned identity (the backfill), or re-fetch the pinned ones. */
  startMetadataLookup: defineAction({
    accept: 'form',
    input: z.object({ mode: z.enum(['backfill', 'refresh']).default('backfill') }),
    handler: async (input, context) => {
      requireOwner(context);
      const refresh = input.mode === 'refresh';
      const mediaIds = refresh ? pinnedMediaIds(db) : unresolvedMediaIds(db);
      if (mediaIds.length === 0) throw new ActionError({ code: 'BAD_REQUEST', message: refresh ? 'Nothing is pinned yet.' : 'Every entry has been looked up.' });
      // A refresh never re-matches, so its result can land without a review. Batches bound what one failure loses.
      let first: number | null = null;
      for (let i = 0; i < mediaIds.length; i += BACKFILL_BATCH) {
        const j = createJob(db, 'lookup_media', { mediaIds: mediaIds.slice(i, i + BACKFILL_BATCH), refresh, auto: refresh });
        first ??= j.id;
      }
      return { returnTo: refresh ? `/jobs?job=${first}` : `/metadata?job=${first}` };
    },
  }),

  /** Commit a lookup's matches: accepted confident ones, and the owner's choice for each unsure one. */
  commitMatches: defineAction({
    accept: 'form',
    input: commitMatchesInput,
    handler: async (input, context) => {
      requireOwner(context);
      const j = jobById(db, input.jobId);
      if (!j || j.status !== 'done') throw new ActionError({ code: 'BAD_REQUEST', message: 'That lookup is no longer open.' });
      const accepted = new Set(input.accept ?? []);
      const choices = input.choice ?? {};
      let committed = 0;
      const refresh: number[] = [];
      for (const v of matchesFor(db, j)) {
        if (v.p.decision !== 'pending') continue;
        const choice = v.payload.status === 'confident' ? (accepted.has(v.p.id) ? 'chosen' : 'skip') : (choices[String(v.p.id)] ?? 'skip');
        if (choice === 'skip') continue;
        if (choice === 'chosen' && v.payload.chosen) {
          commitMatch(db, v.m.id, v.payload);
        } else if (choice === 'none') {
          markNoMatch(db, v.m.id, v.payload.candidates);
        } else if (/^\d+$/.test(choice) && v.payload.candidates[Number(choice)]) {
          const c: Candidate = v.payload.candidates[Number(choice)];
          pinCandidate(db, v.m.id, c, v.payload.candidates);
          refresh.push(v.m.id);
        } else continue;
        db.update(proposal).set({ decision: choice === 'none' ? 'rejected' : 'accepted' }).where(eq(proposal.id, v.p.id)).run();
        committed++;
      }
      if (refresh.length > 0) createJob(db, 'lookup_media', { mediaIds: refresh, refresh: true, auto: true });
      db.update(job).set({ result: JSON.stringify({ ...parseJson<any>(j.result, {}), committed, committedAt: new Date().toISOString() }) }).where(eq(job.id, j.id)).run();
      return { returnTo: `/metadata?job=${j.id}&committed=${committed}` };
    },
  }),

  /** The owner pastes an IMDb, Steam, Goodreads, Wikipedia or Wikidata URL for an entry the lookup could not place. */
  seedMedia: defineAction({
    accept: 'form',
    input: z.object({ mediaId: id, url: z.url().trim(), returnTo }),
    handler: async (input, context) => {
      requireOwner(context);
      const seed = seedFromUrl(input.url);
      if (!seed) throw new ActionError({ code: 'BAD_REQUEST', message: 'That link is not one the lookup understands (IMDb, Steam, Goodreads, Wikipedia or Wikidata).' });
      const m = db.select().from(media).where(eq(media.id, input.mediaId)).get();
      if (!m) throw new ActionError({ code: 'NOT_FOUND', message: 'No such entry.' });
      const ids = { ...seed.ids, ...(seed.wikipedia ? { wikipedia: seed.wikipedia } : {}) };
      const c: Candidate = { qid: seed.qid ?? null, label: m.title, description: '', year: null, creator: m.creator, kinds: [], ids, wikipedia: seed.wikipedia ?? null, score: 1, reasons: ['link from the owner'], source: 'owner' };
      pinCandidate(db, m.id, c, []);
      createJob(db, 'lookup_media', { mediaIds: [m.id], refresh: true, auto: true });
      return { returnTo: input.returnTo ?? `/media/${m.id}` };
    },
  }),

  /** Commit the checked proposals of a job; the rest are remembered as rejected. */
  commitProposals: defineAction({
    accept: 'form',
    input: commitInput,
    handler: async (input, context) => {
      requireOwner(context);
      const accepted = new Set(input.accept ?? []);
      const out = commitProposals(db, input.jobId, accepted, input.prominence ?? {});
      return { returnTo: out.returnTo };
    },
  }),
};

// Jobs and proposals ------------------------------------------------------------
