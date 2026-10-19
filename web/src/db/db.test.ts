import { count } from 'drizzle-orm';
import { describe, expect, it } from 'vitest';
import { openDb } from './open';
import { media } from './schema';

describe('database', () => {
  it('migrates an empty database and round-trips a media row', () => {
    const db = openDb(':memory:');
    db.insert(media).values({ title: 'Pantheon', type: 'TV Series', loggedDate: '2022-11-01', ratingMedium: 5 }).run();
    const [{ n }] = db.select({ n: count() }).from(media).all();
    expect(n).toBe(1);
    const row = db.select().from(media).get();
    expect(row?.title).toBe('Pantheon');
    expect(row?.label).toBeNull();
    expect(row?.createdAt).toMatch(/^\d{4}-\d{2}-\d{2} /);
  });
});
