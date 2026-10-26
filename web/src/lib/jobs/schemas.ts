/** Wire shapes shared by the site and the worker. The worker mirrors these in pydantic. */
import { z } from 'astro/zod';
import { DOSSIER_DEPTHS, JOB_KINDS, PROMINENCES, PROPOSAL_KINDS, SOURCE_KINDS, SUBJECT_KINDS } from '../../db/schema';

export const subjectRef = z.object({ kind: z.enum(SUBJECT_KINDS), id: z.number().int().positive() });

/** scan_trope: an existing trope (tropeId) or a draft one carried in the payload. */
export const scanTropePayload = z.object({
  mode: z.enum(['add', 'recheck']),
  tropeId: z.number().int().positive().optional(),
  draft: z.object({ name: z.string().min(1), description: z.string(), seeds: z.array(z.string()), visual: z.boolean().default(false) }).optional(),
});
/** `auto` marks a job on the automatic path for Notion-synced entries (plan T14): its result is committed without review. */
export const checkSubjectPayload = z.object({ mode: z.enum(['add', 'recheck']), subject: subjectRef, auto: z.boolean().default(false) });
/** `refresh`: the disk chain rebuilt these after new files arrived; rebuilt works get a trope recheck, not the new-entry path. */
export const buildDossiersPayload = z.object({ onlyMissing: z.boolean().default(true), subjects: z.array(subjectRef).optional(), auto: z.boolean().default(false), refresh: z.boolean().default(false) });
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
/** find_evidence: the owner describes the moment they want quoted; the worker searches the work's text and attaches what it finds. */
export const findEvidencePayload = z.object({ instanceId: z.number().int().positive(), prompt: z.string().min(1) });

/** index_local: match these works (or every video and book) to files under the media root. */
export const indexLocalPayload = z.object({ mediaIds: z.array(z.number().int().positive()).optional(), auto: z.boolean().default(false), then: z.enum(['dossier']).optional() });
/** extract_text: subtitles or book text for these local_source rows (or everything not yet indexed). */
export const extractTextPayload = z.object({ sourceIds: z.array(z.number().int().positive()).optional(), auto: z.boolean().default(false), then: z.enum(['dossier']).optional(), mediaIds: z.array(z.number().int().positive()).optional() });
/** make_sheets: contact sheets for these video sources (or every one without sheets); read_sheets: the model's visual notes from them (plan T11). */
export const makeSheetsPayload = z.object({ sourceIds: z.array(z.number().int().positive()).optional(), auto: z.boolean().default(false), then: z.enum(['dossier']).optional(), mediaIds: z.array(z.number().int().positive()).optional() });
export const readSheetsPayload = z.object({ sourceIds: z.array(z.number().int().positive()).optional(), auto: z.boolean().default(false), then: z.enum(['dossier']).optional(), mediaIds: z.array(z.number().int().positive()).optional() });
/** transcribe: Whisper for video sources that had no subtitle from any other source (plan D6). */
export const transcribePayload = z.object({ sourceIds: z.array(z.number().int().positive()).optional(), auto: z.boolean().default(false), model: z.string().optional(), threads: z.number().int().positive().max(48).optional() });
/** look_frames: the model looks at the frames grabbed for a scan's proposals of visual tropes (plan D12). */
export const lookFramesPayload = z.object({ forJob: z.number().int().positive(), auto: z.boolean().default(false) });
/** fetch_wiki: Fandom summaries (and transcripts, when a wiki has them) for pinned works (plan T12). */
export const fetchWikiPayload = z.object({ mediaIds: z.array(z.number().int().positive()).optional(), auto: z.boolean().default(false) });
/** extract_evidence: a frame (or clip) at each timestamped quote; proposals before review, instances after commit. */
export const extractEvidencePayload = z.object({
  items: z.array(z.object({ proposalId: z.number().int().positive().optional(), evidenceId: z.number().int().positive().optional(), sourceId: z.number().int().positive(), at: z.number().min(0), end: z.number().min(0).optional(), clip: z.boolean().default(false) })).min(1),
  /** The scan or check whose proposals these frames belong to, so its review page can wait for them. */
  forJob: z.number().int().positive().optional(),
});

export const payloadByKind = {
  ping: pingPayload,
  build_dossiers: buildDossiersPayload,
  scan_trope: scanTropePayload,
  check_subject: checkSubjectPayload,
  lookup_media: lookupMediaPayload,
  sync_notion: syncNotionPayload,
  write_blurbs: writeBlurbsPayload,
  find_evidence: findEvidencePayload,
  index_local: indexLocalPayload,
  extract_text: extractTextPayload,
  extract_evidence: extractEvidencePayload,
  make_sheets: makeSheetsPayload,
  read_sheets: readSheetsPayload,
  look_frames: lookFramesPayload,
  fetch_wiki: fetchWikiPayload,
  transcribe: transcribePayload,
} as const;
export type JobKind = (typeof JOB_KINDS)[number];

export const progressBody = z.object({ done: z.number().int().min(0), total: z.number().int().min(0), note: z.string().optional() });

/** A quote; from subtitle text it carries `at` (seconds) and, once the media worker has been by, a pending `frame` or `clip` file name. */
export const evidenceItem = z.object({ kind: z.literal('quote'), content: z.string().min(1), locator: z.string().default(''), at: z.number().min(0).optional(), end: z.number().min(0).optional(), frame: z.string().optional(), clip: z.string().optional() });

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
  inputs: z.record(z.string(), z.unknown()).optional(),
});

export const noteIn = z.object({ mediaId: z.number().int().positive(), source: z.enum(['tumblr', 'review', 'manual', 'visual', 'wiki']), url: z.string().nullable().optional(), text: z.string().min(1), label: z.string().default('') });

export const usageIn = z.object({
  model: z.string().optional(),
  calls: z.number().int().min(0).default(0),
  promptTokens: z.number().int().min(0).default(0),
  completionTokens: z.number().int().min(0).default(0),
  cachedTokens: z.number().int().min(0).default(0),
  costUsd: z.number().min(0).optional(),
});

/** look_frames: what the model saw in a proposal's frames. */
export const verdictIn = z.object({ proposalId: z.number().int().positive(), seen: z.boolean(), note: z.string().default('') });

export const resultBody = z.object({
  summary: z.record(z.string(), z.unknown()).default({}),
  proposals: z.array(proposalIn).default([]),
  verdicts: z.array(verdictIn).default([]),
  dossiers: z.array(dossierIn).default([]),
  notes: z.array(noteIn).default([]),
  descriptions: z.array(descriptionIn).default([]),
  usage: usageIn.optional(),
  warnings: z.array(z.string()).default([]),
});

export type ResultBody = z.infer<typeof resultBody>;
export type ProposalIn = z.infer<typeof proposalIn>;

export const dossiersBody = z.object({ dossiers: z.array(dossierIn).default([]), notes: z.array(noteIn).default([]) });

/** A text source the model worker fetched itself (a Fandom transcript), stored under its sources dir. */
export const textLinkBody = z.object({ mediaId: z.number().int().positive(), path: z.string().min(1), label: z.string().default('') });

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

/** What the media worker found on the disk for some works (plan T2). */
export const sourceIn = z.object({
  kind: z.enum(SOURCE_KINDS),
  path: z.string().min(1),
  label: z.string().default(''),
  meta: z.record(z.string(), z.unknown()).default({}),
});
export const sourcesBody = z.object({ works: z.array(z.object({ mediaId: z.number().int().positive(), sources: z.array(sourceIn) })) });


