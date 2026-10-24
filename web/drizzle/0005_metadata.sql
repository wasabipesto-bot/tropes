CREATE TABLE `media_genre` (
	`media_id` integer NOT NULL,
	`genre` text NOT NULL,
	PRIMARY KEY(`media_id`, `genre`),
	FOREIGN KEY (`media_id`) REFERENCES `media`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `media_genre_genre_idx` ON `media_genre` (`genre`);--> statement-breakpoint
CREATE TABLE `media_link` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`media_id` integer NOT NULL,
	`site` text NOT NULL,
	`url` text NOT NULL,
	`score` text,
	`score_value` real,
	`origin` text DEFAULT 'lookup' NOT NULL,
	`hidden` integer DEFAULT false NOT NULL,
	`fetched_at` text DEFAULT (datetime('now')) NOT NULL,
	FOREIGN KEY (`media_id`) REFERENCES `media`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `media_link_media_site` ON `media_link` (`media_id`,`site`);--> statement-breakpoint
CREATE TABLE `trope_alias` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`trope_id` integer NOT NULL,
	`name` text NOT NULL,
	`slug` text NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	FOREIGN KEY (`trope_id`) REFERENCES `trope`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `trope_alias_slug_unique` ON `trope_alias` (`slug`);--> statement-breakpoint
ALTER TABLE `media` ADD `description_origin` text;--> statement-breakpoint
ALTER TABLE `media` ADD `identity` text;--> statement-breakpoint
ALTER TABLE `media` ADD `wikidata_id` text;--> statement-breakpoint
ALTER TABLE `media` ADD `external_ids` text DEFAULT '{}' NOT NULL;--> statement-breakpoint
ALTER TABLE `media` ADD `details` text DEFAULT '{}' NOT NULL;--> statement-breakpoint
ALTER TABLE `media` ADD `identity_candidates` text DEFAULT '[]' NOT NULL;--> statement-breakpoint
ALTER TABLE `media` ADD `wiki_extract` text;--> statement-breakpoint
ALTER TABLE `media` ADD `poster_source` text;--> statement-breakpoint
ALTER TABLE `media` ADD `metadata_at` text;--> statement-breakpoint
ALTER TABLE `media` ADD `genres_edited` integer DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE `media` ADD `notion_missing_since` text;--> statement-breakpoint
ALTER TABLE `media` ADD `review_note` text;--> statement-breakpoint
ALTER TABLE `proposal` ADD `payload` text DEFAULT '{}' NOT NULL;