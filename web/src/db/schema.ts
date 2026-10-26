import { sql } from 'drizzle-orm';
import { index, integer, primaryKey, real, sqliteTable, text, uniqueIndex } from 'drizzle-orm/sqlite-core';

export const MEDIA_TYPES = ['Book', 'TV Series', 'Movie', 'Game', 'Podcast', 'Album', 'Other'] as const;
export type MediaType = (typeof MEDIA_TYPES)[number];
export const DESCRIPTION_ORIGINS = ['owner', 'model'] as const;
/** pinned: identity confirmed (by a confident lookup or the owner); check: a lookup was unsure, waiting in /review;
 *  not_found: nothing matched, tried again by the next backfill; none: the owner said there is no public match. */
export const IDENTITY_STATES = ['pinned', 'check', 'not_found', 'none'] as const;
export type IdentityState = (typeof IDENTITY_STATES)[number];

const timestamps = {
  createdAt: text('created_at').notNull().default(sql`(datetime('now'))`),
  updatedAt: text('updated_at').notNull().default(sql`(datetime('now'))`),
};

/** One log entry. Notion owns the fields it supplies; everything else is site-only. */
export const media = sqliteTable(
  'media',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    notionId: text('notion_id').unique(),
    title: text('title').notNull(),
    type: text('type', { enum: MEDIA_TYPES }).notNull(),
    /** Display label when the type is not specific enough ("web serial"). Null means derive from type. */
    label: text('label'),
    creator: text('creator'),
    /** ISO date, null for the ~175 undated entries. */
    loggedDate: text('logged_date'),
    description: text('description'),
    posterPath: text('poster_path'),
    /** Notion's Image Link and Media Link, kept verbatim; posters are fetched from the former in Phase 4. */
    notionImageUrl: text('notion_image_url'),
    notionMediaUrl: text('notion_media_url'),
    localRoot: text('local_root'),
    /** Who wrote the description: the owner, or the model's draft blurb (shown with a quiet mark to the owner). */
    descriptionOrigin: text('description_origin', { enum: DESCRIPTION_ORIGINS }),
    /** The pinned public identity (Phase 4). Null until a lookup ran; see IDENTITY_STATES. */
    identity: text('identity', { enum: IDENTITY_STATES }),
    wikidataId: text('wikidata_id'),
    /** JSON {imdb, tmdb_tv, tmdb_movie, tvdb, mal, steam, openlibrary, musicbrainz_rg, itunes, goodreads, …}. */
    externalIds: text('external_ids').notNull().default('{}'),
    /** JSON, fields by type: start, end, seasons, episodes, runtime_min, studio, network, developer, publisher, tracks, … */
    details: text('details').notNull().default('{}'),
    /** JSON list of the lookup's runners-up, so "Wrong match" can offer them without another search. */
    identityCandidates: text('identity_candidates').notNull().default('[]'),
    /** Wikipedia's lead paragraph. Internal: a dossier input and a reference beside the description field. */
    wikiExtract: text('wiki_extract'),
    /** URL the stored poster came from; a changed Notion Image Link no longer matches and triggers a re-fetch. */
    posterSource: text('poster_source'),
    metadataAt: text('metadata_at'),
    /** Once the owner edits genres, a refresh leaves them alone. */
    genresEdited: integer('genres_edited', { mode: 'boolean' }).notNull().default(false),
    /** Set by the Notion sync when a row with this id stopped coming back; cleared when it returns. */
    notionMissingSince: text('notion_missing_since'),
    /** A short note for /review, set by the sync ("Media Link changed since the match was pinned"). */
    reviewNote: text('review_note'),
    ratingMedium: real('rating_medium'),
    ratingStory: real('rating_story'),
    ratingTone: real('rating_tone'),
    ratingEnjoyability: real('rating_enjoyability'),
    ratingEffect: real('rating_effect'),
    ...timestamps,
  },
  (t) => [index('media_logged_date_idx').on(t.loggedDate), index('media_title_idx').on(t.title)],
);

export type Media = typeof media.$inferSelect;
export type NewMedia = typeof media.$inferInsert;

export const LINK_ORIGINS = ['lookup', 'notion', 'owner'] as const;

/** One external link per site per work, with its score where the site has one ("77", "100%", "6.21"). */
export const mediaLink = sqliteTable(
  'media_link',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    mediaId: integer('media_id').notNull().references(() => media.id, { onDelete: 'cascade' }),
    /** Site key: wikipedia, imdb, tmdb, tvdb, mal, anidb, ann, rt, metacritic, steam, goodreads, openlibrary, musicbrainz, spotify, bandcamp, itunes, letterboxd, official. */
    site: text('site').notNull(),
    url: text('url').notNull(),
    score: text('score'),
    scoreValue: real('score_value'),
    origin: text('origin', { enum: LINK_ORIGINS }).notNull().default('lookup'),
    hidden: integer('hidden', { mode: 'boolean' }).notNull().default(false),
    fetchedAt: text('fetched_at').notNull().default(sql`(datetime('now'))`),
  },
  (t) => [uniqueIndex('media_link_media_site').on(t.mediaId, t.site)],
);

/** Genres from the controlled vocabulary in web/seed/genres.json. */
export const mediaGenre = sqliteTable(
  'media_genre',
  {
    mediaId: integer('media_id').notNull().references(() => media.id, { onDelete: 'cascade' }),
    genre: text('genre').notNull(),
  },
  (t) => [primaryKey({ columns: [t.mediaId, t.genre] }), index('media_genre_genre_idx').on(t.genre)],
);

export type MediaLink = typeof mediaLink.$inferSelect;

/** Several log entries that count as one work for trope purposes (Terra Ignota, the Murderbot books). */
export const series = sqliteTable('series', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  name: text('name').notNull().unique(),
  slug: text('slug').notNull().unique(),
  description: text('description'),
  ...timestamps,
});

export const seriesMember = sqliteTable(
  'series_member',
  {
    seriesId: integer('series_id').notNull().references(() => series.id, { onDelete: 'cascade' }),
    mediaId: integer('media_id').notNull().references(() => media.id, { onDelete: 'cascade' }),
    position: integer('position').notNull().default(0),
  },
  (t) => [primaryKey({ columns: [t.seriesId, t.mediaId] })],
);

export const trope = sqliteTable('trope', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  name: text('name').notNull().unique(),
  slug: text('slug').notNull().unique(),
  /** Also the prompt the matcher reads. Supports [[links]] and ||spoilers||. */
  description: text('description').notNull().default(''),
  /** "Visual trope, use screenshots": the model checks the frame at each candidate moment before proposing (plan D12). */
  visual: integer('visual', { mode: 'boolean' }).notNull().default(false),
  ...timestamps,
});

/** Example titles given when the trope was created, kept as typed, resolved to a media row when one matches. */
export const tropeSeed = sqliteTable('trope_seed', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tropeId: integer('trope_id').notNull().references(() => trope.id, { onDelete: 'cascade' }),
  title: text('title').notNull(),
  mediaId: integer('media_id').references(() => media.id, { onDelete: 'set null' }),
});

/** Former names of a renamed trope: old URLs redirect and old [[links]] still resolve. */
export const tropeAlias = sqliteTable('trope_alias', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tropeId: integer('trope_id').notNull().references(() => trope.id, { onDelete: 'cascade' }),
  name: text('name').notNull(),
  slug: text('slug').notNull().unique(),
  createdAt: text('created_at').notNull().default(sql`(datetime('now'))`),
});

export const PROMINENCES = ['core', 'recurring', 'brief'] as const;
export type Prominence = (typeof PROMINENCES)[number];
export const SUBJECT_KINDS = ['media', 'series'] as const;
export type SubjectKind = (typeof SUBJECT_KINDS)[number];
/** model: proposed by a scan and committed by the owner; manual: typed in; auto: committed by the automatic path without review. */
export const ORIGINS = ['model', 'manual', 'auto'] as const;

/** A trope ↔ work association. The subject is a media row or a series row. */
export const instance = sqliteTable(
  'instance',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    tropeId: integer('trope_id').notNull().references(() => trope.id, { onDelete: 'cascade' }),
    subjectKind: text('subject_kind', { enum: SUBJECT_KINDS }).notNull(),
    subjectId: integer('subject_id').notNull(),
    /** The character, pair or element: "Viv and Zanj", "MIST". */
    who: text('who').notNull().default(''),
    text: text('text').notNull().default(''),
    prominence: text('prominence', { enum: PROMINENCES }).notNull().default('brief'),
    verified: integer('verified', { mode: 'boolean' }).notNull().default(false),
    /** The model's calibration score when found; null for manual entries. Never shown on trope or media pages. */
    score: real('score'),
    origin: text('origin', { enum: ORIGINS }).notNull().default('manual'),
    ...timestamps,
  },
  (t) => [index('instance_trope_idx').on(t.tropeId), index('instance_subject_idx').on(t.subjectKind, t.subjectId)],
);

export const notable = sqliteTable(
  'notable',
  {
    tropeId: integer('trope_id').notNull().references(() => trope.id, { onDelete: 'cascade' }),
    instanceId: integer('instance_id').notNull().references(() => instance.id, { onDelete: 'cascade' }),
    position: integer('position').notNull().default(0),
  },
  (t) => [primaryKey({ columns: [t.tropeId, t.instanceId] })],
);

export const EVIDENCE_KINDS = ['quote', 'frame', 'clip'] as const;

export const evidence = sqliteTable('evidence', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  instanceId: integer('instance_id').notNull().references(() => instance.id, { onDelete: 'cascade' }),
  kind: text('kind', { enum: EVIDENCE_KINDS }).notNull(),
  /** "ch. 12", "S01E03 12:40", "S01E05 3:10–3:42", an EPUB CFI. */
  locator: text('locator').notNull().default(''),
  /** Quote text for quotes; null for frames and clips. */
  content: text('content'),
  filePath: text('file_path'),
  width: integer('width'),
  height: integer('height'),
  durationMs: integer('duration_ms'),
  /** False hides it from anonymous visitors (fair-use caps) without deleting it. */
  public: integer('public', { mode: 'boolean' }).notNull().default(true),
  position: integer('position').notNull().default(0),
  createdAt: text('created_at').notNull().default(sql`(datetime('now'))`),
});

/** Owner login sessions. One owner, so no user column. */
export const session = sqliteTable('session', {
  id: text('id').primaryKey(),
  createdAt: text('created_at').notNull().default(sql`(datetime('now'))`),
  expiresAt: text('expires_at').notNull(),
  userAgent: text('user_agent'),
});

export type Series = typeof series.$inferSelect;
export type Trope = typeof trope.$inferSelect;
export type Instance = typeof instance.$inferSelect;
export type Evidence = typeof evidence.$inferSelect;

export const SOURCE_KINDS = ['text', 'video', 'subtitle', 'audio', 'book'] as const;

/**
 * A file for a work: a text the owner linked (Phase 3), or what the media worker found on the disk
 * (Phase 5): one row per episode file or film file, one per Calibre book. `path` is relative to the
 * media root for disk files and to the sources directory for linked texts.
 */
export const localSource = sqliteTable('local_source', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  mediaId: integer('media_id').notNull().references(() => media.id, { onDelete: 'cascade' }),
  kind: text('kind', { enum: SOURCE_KINDS }).notNull(),
  path: text('path').notNull(),
  /** "S01E03" for an episode; empty for a film or a book. */
  label: text('label').notNull().default(''),
  /** JSON: duration, subtitle streams, sidecar subtitles, the text source chosen, the Calibre book id, formats. */
  meta: text('meta').notNull().default('{}'),
  /** Set once the media worker has extracted this file's text (or decided it has none). */
  indexedAt: text('indexed_at'),
  createdAt: text('created_at').notNull().default(sql`(datetime('now'))`),
});

/** Something the owner wrote about a work, found on Tumblr or injected by hand. Feeds the dossier. */
export const mediaNote = sqliteTable('media_note', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  mediaId: integer('media_id').notNull().references(() => media.id, { onDelete: 'cascade' }),
  /** tumblr/review/manual: the owner's words; visual: what the model saw on a contact sheet of one episode (Phase 5 T11); wiki: a Fandom summary (T12). */
  source: text('source', { enum: ['tumblr', 'review', 'manual', 'visual', 'wiki'] }).notNull(),
  /** "S01E03" for a per-episode note. */
  label: text('label').notNull().default(''),
  url: text('url'),
  text: text('text').notNull(),
  fetchedAt: text('fetched_at').notNull().default(sql`(datetime('now'))`),
});

export const JOB_KINDS = ['ping', 'build_dossiers', 'scan_trope', 'check_subject', 'lookup_media', 'sync_notion', 'write_blurbs', 'find_evidence', 'index_local', 'extract_text', 'extract_evidence', 'make_sheets', 'read_sheets', 'look_frames', 'fetch_wiki'] as const;
/** Job kinds that read the media disk; the media worker on celebrimbor claims these and nothing else. */
export const MEDIA_JOB_KINDS = ['index_local', 'extract_text', 'extract_evidence', 'make_sheets'] as const;
export const JOB_STATUSES = ['queued', 'running', 'done', 'failed', 'cancelled'] as const;

/** Work handed to the worker. Payload and result are JSON validated by zod on the site and pydantic in the worker. */
export const job = sqliteTable('job', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  kind: text('kind', { enum: JOB_KINDS }).notNull(),
  payload: text('payload').notNull().default('{}'),
  status: text('status', { enum: JOB_STATUSES }).notNull().default('queued'),
  progress: text('progress'),
  result: text('result'),
  error: text('error'),
  usage: text('usage'),
  attempts: integer('attempts').notNull().default(0),
  createdAt: text('created_at').notNull().default(sql`(datetime('now'))`),
  claimedAt: text('claimed_at'),
  heartbeatAt: text('heartbeat_at'),
  finishedAt: text('finished_at'),
});

export const PROPOSAL_KINDS = ['instance', 'evidence', 'match'] as const;
export const DECISIONS = ['pending', 'accepted', 'rejected'] as const;

/** One suggestion from a job, waiting for the owner. Committing turns accepted ones into instances or evidence. */
export const proposal = sqliteTable(
  'proposal',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    jobId: integer('job_id').notNull().references(() => job.id, { onDelete: 'cascade' }),
    /** Null while the trope only exists in the job payload (add-trope flow); set at commit. */
    tropeId: integer('trope_id').references(() => trope.id, { onDelete: 'cascade' }),
    subjectKind: text('subject_kind', { enum: SUBJECT_KINDS }).notNull(),
    subjectId: integer('subject_id').notNull(),
    kind: text('kind', { enum: PROPOSAL_KINDS }).notNull().default('instance'),
    /** For evidence proposals: the existing instance the evidence belongs to. */
    targetInstanceId: integer('target_instance_id').references(() => instance.id, { onDelete: 'cascade' }),
    score: real('score').notNull().default(0),
    prominence: text('prominence', { enum: PROMINENCES }).notNull().default('brief'),
    who: text('who').notNull().default(''),
    text: text('text').notNull().default(''),
    /** JSON list of {kind, content, locator}. */
    evidence: text('evidence').notNull().default('[]'),
    /** One of the owner's seed examples for this trope. */
    seed: integer('seed', { mode: 'boolean' }).notNull().default(false),
    /** The owner left this subject unchecked for this trope before; shown last. */
    rejectedBefore: integer('rejected_before', { mode: 'boolean' }).notNull().default(false),
    /** JSON list of warnings: writing check tripped twice, quotes dropped, and so on. */
    flags: text('flags').notNull().default('[]'),
    /** For match proposals (lookup_media): the resolved identity, candidates, details, links, genres and poster. */
    payload: text('payload').notNull().default('{}'),
    decision: text('decision', { enum: DECISIONS }).notNull().default('pending'),
    createdAt: text('created_at').notNull().default(sql`(datetime('now'))`),
  },
  (t) => [index('proposal_job_idx').on(t.jobId), index('proposal_trope_idx').on(t.tropeId)],
);

export const DOSSIER_DEPTHS = ['knowledge', 'text'] as const;

/** The per-work summary the matcher reads. Internal; never shown on the site. */
export const dossier = sqliteTable(
  'dossier',
  {
    subjectKind: text('subject_kind', { enum: SUBJECT_KINDS }).notNull(),
    subjectId: integer('subject_id').notNull(),
    depth: text('depth', { enum: DOSSIER_DEPTHS }).notNull(),
    body: text('body').notNull(),
    model: text('model').notNull(),
    promptVersion: integer('prompt_version').notNull(),
    sourceHash: text('source_hash'),
    builtAt: text('built_at').notNull().default(sql`(datetime('now'))`),
  },
  (t) => [primaryKey({ columns: [t.subjectKind, t.subjectId] })],
);

/** Bearer tokens for the worker. The token is shown once; only its hash is stored. */
export const apiKey = sqliteTable('api_key', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  name: text('name').notNull(),
  hash: text('hash').notNull().unique(),
  createdAt: text('created_at').notNull().default(sql`(datetime('now'))`),
  lastUsedAt: text('last_used_at'),
});

export type Job = typeof job.$inferSelect;
export type Proposal = typeof proposal.$inferSelect;
export type Dossier = typeof dossier.$inferSelect;
