import { sql } from 'drizzle-orm';
import { index, integer, real, sqliteTable, text } from 'drizzle-orm/sqlite-core';

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
