CREATE VIRTUAL TABLE media_fts USING fts5(title, creator, content='media', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
--> statement-breakpoint
CREATE TRIGGER media_fts_ai AFTER INSERT ON media BEGIN
  INSERT INTO media_fts(rowid, title, creator) VALUES (new.id, new.title, new.creator);
END;
--> statement-breakpoint
CREATE TRIGGER media_fts_ad AFTER DELETE ON media BEGIN
  INSERT INTO media_fts(media_fts, rowid, title, creator) VALUES ('delete', old.id, old.title, old.creator);
END;
--> statement-breakpoint
CREATE TRIGGER media_fts_au AFTER UPDATE OF title, creator ON media BEGIN
  INSERT INTO media_fts(media_fts, rowid, title, creator) VALUES ('delete', old.id, old.title, old.creator);
  INSERT INTO media_fts(rowid, title, creator) VALUES (new.id, new.title, new.creator);
END;
