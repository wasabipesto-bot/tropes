import { sql } from 'drizzle-orm';
import { index, integer, primaryKey, real, sqliteTable, text } from 'drizzle-orm/sqlite-core';

export const MEDIA_TYPES = ['Book', 'TV Series', 'Movie', 'Game', 'Podcast', 'Album', 'Other'] as const;
export type MediaType = (typeof MEDIA_TYPES)[number];

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
  ...timestamps,
});

/** Example titles given when the trope was created, kept as typed, resolved to a media row when one matches. */
export const tropeSeed = sqliteTable('trope_seed', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  tropeId: integer('trope_id').notNull().references(() => trope.id, { onDelete: 'cascade' }),
  title: text('title').notNull(),
  mediaId: integer('media_id').references(() => media.id, { onDelete: 'set null' }),
});

export const PROMINENCES = ['core', 'recurring', 'brief'] as const;
export type Prominence = (typeof PROMINENCES)[number];
export const SUBJECT_KINDS = ['media', 'series'] as const;
export type SubjectKind = (typeof SUBJECT_KINDS)[number];
export const ORIGINS = ['model', 'manual'] as const;

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
