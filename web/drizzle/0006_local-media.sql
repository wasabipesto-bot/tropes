ALTER TABLE `local_source` ADD `label` text DEFAULT '' NOT NULL;--> statement-breakpoint
ALTER TABLE `local_source` ADD `meta` text DEFAULT '{}' NOT NULL;--> statement-breakpoint
ALTER TABLE `local_source` ADD `indexed_at` text;--> statement-breakpoint
ALTER TABLE `media_note` ADD `label` text DEFAULT '' NOT NULL;