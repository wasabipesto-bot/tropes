CREATE TABLE `evidence` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`instance_id` integer NOT NULL,
	`kind` text NOT NULL,
	`locator` text DEFAULT '' NOT NULL,
	`content` text,
	`file_path` text,
	`width` integer,
	`height` integer,
	`duration_ms` integer,
	`public` integer DEFAULT true NOT NULL,
	`position` integer DEFAULT 0 NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	FOREIGN KEY (`instance_id`) REFERENCES `instance`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `instance` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`trope_id` integer NOT NULL,
	`subject_kind` text NOT NULL,
	`subject_id` integer NOT NULL,
	`who` text DEFAULT '' NOT NULL,
	`text` text DEFAULT '' NOT NULL,
	`prominence` text DEFAULT 'brief' NOT NULL,
	`verified` integer DEFAULT false NOT NULL,
	`score` real,
	`origin` text DEFAULT 'manual' NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	`updated_at` text DEFAULT (datetime('now')) NOT NULL,
	FOREIGN KEY (`trope_id`) REFERENCES `trope`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `instance_trope_idx` ON `instance` (`trope_id`);--> statement-breakpoint
CREATE INDEX `instance_subject_idx` ON `instance` (`subject_kind`,`subject_id`);--> statement-breakpoint
CREATE TABLE `notable` (
	`trope_id` integer NOT NULL,
	`instance_id` integer NOT NULL,
	`position` integer DEFAULT 0 NOT NULL,
	PRIMARY KEY(`trope_id`, `instance_id`),
	FOREIGN KEY (`trope_id`) REFERENCES `trope`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`instance_id`) REFERENCES `instance`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `series` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`slug` text NOT NULL,
	`description` text,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	`updated_at` text DEFAULT (datetime('now')) NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `series_name_unique` ON `series` (`name`);--> statement-breakpoint
CREATE UNIQUE INDEX `series_slug_unique` ON `series` (`slug`);--> statement-breakpoint
CREATE TABLE `series_member` (
	`series_id` integer NOT NULL,
	`media_id` integer NOT NULL,
	`position` integer DEFAULT 0 NOT NULL,
	PRIMARY KEY(`series_id`, `media_id`),
	FOREIGN KEY (`series_id`) REFERENCES `series`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`media_id`) REFERENCES `media`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `session` (
	`id` text PRIMARY KEY NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	`expires_at` text NOT NULL,
	`user_agent` text
);
--> statement-breakpoint
CREATE TABLE `trope` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`slug` text NOT NULL,
	`description` text DEFAULT '' NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	`updated_at` text DEFAULT (datetime('now')) NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `trope_name_unique` ON `trope` (`name`);--> statement-breakpoint
CREATE UNIQUE INDEX `trope_slug_unique` ON `trope` (`slug`);--> statement-breakpoint
CREATE TABLE `trope_seed` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`trope_id` integer NOT NULL,
	`title` text NOT NULL,
	`media_id` integer,
	FOREIGN KEY (`trope_id`) REFERENCES `trope`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`media_id`) REFERENCES `media`(`id`) ON UPDATE no action ON DELETE set null
);
