import { ActionError, defineAction } from 'astro:actions';
import { getSecret } from 'astro:env/server';
import { z } from 'astro/zod';
import { and, eq, sql } from 'drizzle-orm';
import type { ActionAPIContext } from 'astro:actions';
import { db } from '../db';
import { MEDIA_TYPES, PROMINENCES, evidence, instance, media, notable, proposal, series, trope, tropeSeed } from '../db/schema';
import { cancelJob, createJob, jobById } from '../lib/jobs/queue';
import { commitProposals } from '../lib/jobs/commit';
import { commitInput } from '../lib/jobs/forms';
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
