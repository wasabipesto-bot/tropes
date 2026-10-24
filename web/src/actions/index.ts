import { ActionError, defineAction } from 'astro:actions';
import { getSecret } from 'astro:env/server';
import { z } from 'astro/zod';
import { and, eq, sql } from 'drizzle-orm';
import type { ActionAPIContext } from 'astro:actions';
import { db } from '../db';
import { MEDIA_TYPES, PROMINENCES, evidence, instance, job, media, notable, proposal, series, trope, tropeSeed } from '../db/schema';
import { cancelJob, createJob, jobById, parseJson } from '../lib/jobs/queue';
import { commitProposals } from '../lib/jobs/commit';
import { commitInput, commitMatchesInput } from '../lib/jobs/forms';
import { BACKFILL_BATCH, matchesFor, pinnedMediaIds, unresolvedMediaIds } from '../lib/jobs/matches';
import { commitMatch, markNoMatch, pinCandidate, type Candidate } from '../lib/metadata';
import { seedFromUrl } from '../lib/seeds';
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

  createMedia: defineAction({
    accept: 'form',
    input: z.object({ title: z.string().trim().min(1), type: z.enum(MEDIA_TYPES), creator: z.string().trim().optional() }),
    handler: async (input, context) => {
      requireOwner(context);
      const created = db.insert(media).values({ title: input.title, type: input.type, creator: input.creator || null }).returning().get();
      return { returnTo: `/media/${created.id}` };
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

  /** Add-media (Phase 3 form): the title must already be in the library; then check it against every trope. */
  startSubjectCheck: defineAction({
    accept: 'form',
    input: z.object({ title: z.string().trim().optional(), subjectKind: z.enum(['media', 'series']).optional(), subjectId: id.optional(), mode: z.enum(['add', 'recheck']).default('add') }),
    handler: async (input, context) => {
      requireOwner(context);
      const subject = input.subjectKind && input.subjectId ? { kind: input.subjectKind, id: input.subjectId } : resolveSubject(db, input.title ?? '');
      if (!subject) throw new ActionError({ code: 'NOT_FOUND', message: `Nothing in the library is called “${input.title ?? ''}”. Import it from Notion or create it below first.` });
      const j = createJob(db, 'check_subject', { mode: input.mode, subject });
      const back = subject.kind === 'media' ? `/recheck/media/${subject.id}` : `/recheck/series/${subject.id}`;
      return { returnTo: input.mode === 'add' ? `/add/media?job=${j.id}` : `${back}?job=${j.id}` };
    },
  }),

  startDossierBuild: defineAction({
    accept: 'form',
    input: z.object({ onlyMissing: z.coerce.boolean().default(true) }),
    handler: async (input, context) => {
      requireOwner(context);
      const j = createJob(db, 'build_dossiers', { onlyMissing: input.onlyMissing });
      return { returnTo: `/jobs?job=${j.id}` };
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
    input: z.object({ mediaId: id, url: z.string().trim().url(), returnTo }),
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
