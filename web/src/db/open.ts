import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { migrate } from 'drizzle-orm/better-sqlite3/migrator';
import * as schema from './schema';

export type Db = ReturnType<typeof openDb>;

/**
 * Open (creating if needed) the SQLite database and bring it up to date.
 * The site is the only writer; the worker goes through the HTTP API.
 */
export function openDb(path = process.env.DATABASE_PATH ?? './data/tropes.db') {
  if (path !== ':memory:') mkdirSync(dirname(resolve(path)), { recursive: true });
  const sqlite = new Database(path);
  sqlite.pragma('journal_mode = WAL');
  sqlite.pragma('foreign_keys = ON');
  sqlite.pragma('busy_timeout = 5000');
  const db = drizzle({ client: sqlite, schema });
  migrate(db, { migrationsFolder: process.env.MIGRATIONS_DIR ?? resolve(process.cwd(), 'drizzle') });
  return db;
}
