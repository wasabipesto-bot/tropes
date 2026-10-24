/** Wire shapes shared by the site and the worker. The worker mirrors these in pydantic. */
import { z } from 'astro/zod';
import { DOSSIER_DEPTHS, JOB_KINDS, PROMINENCES, PROPOSAL_KINDS, SUBJECT_KINDS } from '../../db/schema';

export const subjectRef = z.object({ kind: z.enum(SUBJECT_KINDS), id: z.number().int().positive() });

/** scan_trope: an existing trope (tropeId) or a draft one carried in the payload. */
export const scanTropePayload = z.object({
  mode: z.enum(['add', 'recheck']),
  tropeId: z.number().int().positive().optional(),
  draft: z.object({ name: z.string().min(1), description: z.string(), seeds: z.array(z.string()) }).optional(),
});
/** `auto` marks a job on the automatic path for Notion-synced entries (plan T14): its result is committed without review. */
export const checkSubjectPayload = z.object({ mode: z.enum(['add', 'recheck']), subject: subjectRef, auto: z.boolean().default(false) });
export const buildDossiersPayload = z.object({ onlyMissing: z.boolean().default(true), subjects: z.array(subjectRef).optional(), auto: z.boolean().default(false) });
export const pingPayload = z.object({});
/** lookup_media: resolve and fetch metadata for these works. `refresh` re-fetches from the pinned identity and never re-matches. */
export const lookupMediaPayload = z.object({
  mediaIds: z.array(z.number().int().positive()).min(1),
  auto: z.boolean().default(false),
  refresh: z.boolean().default(false),
  /** A poster URL the owner picked; the worker tries it first. */
  poster: z.string().optional(),
});
export const syncNotionPayload = z.object({});
export const writeBlurbsPayload = z.object({ mediaIds: z.array(z.number().int().positive()).min(1), auto: z.boolean().default(false) });

export const payloadByKind = {
  ping: pingPayload,
  build_dossiers: buildDossiersPayload,
  scan_trope: scanTropePayload,
  check_subject: checkSubjectPayload,
  lookup_media: lookupMediaPayload,
  sync_notion: syncNotionPayload,
  write_blurbs: writeBlurbsPayload,
} as const;
export type JobKind = (typeof JOB_KINDS)[number];

export const progressBody = z.object({ done: z.number().int().min(0), total: z.number().int().min(0), note: z.string().optional() });

export const evidenceItem = z.object({ kind: z.literal('quote'), content: z.string().min(1), locator: z.string().default('') });

export const proposalIn = z.object({
  tropeId: z.number().int().positive().nullable().optional(),
  subject: subjectRef,
  kind: z.enum(PROPOSAL_KINDS).default('instance'),
  targetInstanceId: z.number().int().positive().nullable().optional(),
  score: z.number().min(0).max(1),
  prominence: z.enum(PROMINENCES).default('brief'),
  who: z.string().default(''),
  text: z.string().default(''),
  evidence: z.array(evidenceItem).default([]),
  seed: z.boolean().default(false),
  rejectedBefore: z.boolean().default(false),
  flags: z.array(z.string()).default([]),
  /** Match proposals (lookup_media) carry the whole lookup result here; see lib/metadata.ts MatchPayload. */
  payload: z.record(z.string(), z.unknown()).default({}),
});

/** A model-written description draft (write_blurbs). Stored only where the owner has not written one. */
export const descriptionIn = z.object({ mediaId: z.number().int().positive(), text: z.string().min(1) });

export const dossierIn = z.object({
  subject: subjectRef,
  depth: z.enum(DOSSIER_DEPTHS),
  body: z.record(z.string(), z.unknown()),
  model: z.string(),
  promptVersion: z.number().int(),
  sourceHash: z.string().nullable().optional(),
});

export const noteIn = z.object({ mediaId: z.number().int().positive(), source: z.enum(['tumblr', 'review', 'manual']), url: z.string().nullable().optional(), text: z.string().min(1) });

export const usageIn = z.object({
  model: z.string().optional(),
  calls: z.number().int().min(0).default(0),
  promptTokens: z.number().int().min(0).default(0),
  completionTokens: z.number().int().min(0).default(0),
  cachedTokens: z.number().int().min(0).default(0),
  costUsd: z.number().min(0).optional(),
});

export const resultBody = z.object({
  summary: z.record(z.string(), z.unknown()).default({}),
  proposals: z.array(proposalIn).default([]),
  dossiers: z.array(dossierIn).default([]),
  notes: z.array(noteIn).default([]),
  descriptions: z.array(descriptionIn).default([]),
  usage: usageIn.optional(),
  warnings: z.array(z.string()).default([]),
});

export type ResultBody = z.infer<typeof resultBody>;
export type ProposalIn = z.infer<typeof proposalIn>;

export const dossiersBody = z.object({ dossiers: z.array(dossierIn).default([]), notes: z.array(noteIn).default([]) });

/** A Media Log row as the worker reads it from Notion; the same shape the CSV importer builds. */
export const logRowIn = z.object({
  notionId: z.string().nullable(),
  title: z.string().min(1),
  type: z.string(),
  creator: z.string().nullable(),
  loggedDate: z.string().nullable(),
  ratings: z.object({ medium: z.number().nullable(), story: z.number().nullable(), tone: z.number().nullable(), enjoyability: z.number().nullable(), effect: z.number().nullable() }),
  imageUrl: z.string().nullable(),
  mediaUrl: z.string().nullable(),
});
export const notionImportBody = z.object({ rows: z.array(logRowIn), complete: z.boolean().default(false) });

export const createJobBody = z.object({ kind: z.enum(JOB_KINDS), payload: z.record(z.string(), z.unknown()).default({}) });
