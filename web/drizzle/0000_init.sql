CREATE TABLE `media` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`notion_id` text,
	`title` text NOT NULL,
	`type` text NOT NULL,
	`label` text,
	`creator` text,
	`logged_date` text,
	`description` text,
	`poster_path` text,
	`local_root` text,
	`rating_medium` real,
	`rating_story` real,
	`rating_tone` real,
	`rating_enjoyability` real,
	`rating_effect` real,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	`updated_at` text DEFAULT (datetime('now')) NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `media_notion_id_unique` ON `media` (`notion_id`);--> statement-breakpoint
CREATE INDEX `media_logged_date_idx` ON `media` (`logged_date`);--> statement-breakpoint
CREATE INDEX `media_title_idx` ON `media` (`title`);