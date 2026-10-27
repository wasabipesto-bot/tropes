CREATE TABLE `media_video` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`media_id` integer NOT NULL,
	`kind` text NOT NULL,
	`provider` text NOT NULL,
	`url` text NOT NULL,
	`label` text DEFAULT '' NOT NULL,
	`origin` text DEFAULT 'owner' NOT NULL,
	`source_url` text,
	`position` integer DEFAULT 0 NOT NULL,
	`hidden` integer DEFAULT false NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	FOREIGN KEY (`media_id`) REFERENCES `media`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `media_video_media_url` ON `media_video` (`media_id`,`url`);