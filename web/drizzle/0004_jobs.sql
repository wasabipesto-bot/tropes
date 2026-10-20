CREATE TABLE `api_key` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`hash` text NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	`last_used_at` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `api_key_hash_unique` ON `api_key` (`hash`);--> statement-breakpoint
CREATE TABLE `dossier` (
	`subject_kind` text NOT NULL,
	`subject_id` integer NOT NULL,
	`depth` text NOT NULL,
	`body` text NOT NULL,
	`model` text NOT NULL,
	`prompt_version` integer NOT NULL,
	`source_hash` text,
	`built_at` text DEFAULT (datetime('now')) NOT NULL,
	PRIMARY KEY(`subject_kind`, `subject_id`)
);
--> statement-breakpoint
CREATE TABLE `job` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`kind` text NOT NULL,
	`payload` text DEFAULT '{}' NOT NULL,
	`status` text DEFAULT 'queued' NOT NULL,
	`progress` text,
	`result` text,
	`error` text,
	`usage` text,
	`attempts` integer DEFAULT 0 NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	`claimed_at` text,
	`heartbeat_at` text,
	`finished_at` text
);
--> statement-breakpoint
CREATE TABLE `local_source` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`media_id` integer NOT NULL,
	`kind` text NOT NULL,
	`path` text NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	FOREIGN KEY (`media_id`) REFERENCES `media`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `media_note` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`media_id` integer NOT NULL,
	`source` text NOT NULL,
	`url` text,
	`text` text NOT NULL,
	`fetched_at` text DEFAULT (datetime('now')) NOT NULL,
	FOREIGN KEY (`media_id`) REFERENCES `media`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `proposal` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`job_id` integer NOT NULL,
	`trope_id` integer,
	`subject_kind` text NOT NULL,
	`subject_id` integer NOT NULL,
	`kind` text DEFAULT 'instance' NOT NULL,
	`target_instance_id` integer,
	`score` real DEFAULT 0 NOT NULL,
	`prominence` text DEFAULT 'brief' NOT NULL,
	`who` text DEFAULT '' NOT NULL,
	`text` text DEFAULT '' NOT NULL,
	`evidence` text DEFAULT '[]' NOT NULL,
	`seed` integer DEFAULT false NOT NULL,
	`rejected_before` integer DEFAULT false NOT NULL,
	`flags` text DEFAULT '[]' NOT NULL,
	`decision` text DEFAULT 'pending' NOT NULL,
	`created_at` text DEFAULT (datetime('now')) NOT NULL,
	FOREIGN KEY (`job_id`) REFERENCES `job`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`trope_id`) REFERENCES `trope`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`target_instance_id`) REFERENCES `instance`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `proposal_job_idx` ON `proposal` (`job_id`);--> statement-breakpoint
CREATE INDEX `proposal_trope_idx` ON `proposal` (`trope_id`);