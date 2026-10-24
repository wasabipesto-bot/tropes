import { describe, expect, it } from 'vitest';
import { openDb } from '../db/open';
import { media } from '../db/schema';
import { importCsv, importNotionRows, parseNotionDate } from './notion-import';
import { searchMedia } from './search';

const csv = `﻿Title,Type,Artist/Developer,Medium,Story,Tone,Enjoyability,Effect,Average Rating,Date,Image Link,Media Link
Pantheon,TV Series,AMC,5,4,4,4.5,5,4.5,"November 1, 2022",https://theposterdb.com/api/assets/263743,https://www.imdb.com/title/tt11680642/
"Good Luck, Have Fun, Don't Die",Movie,Gore Verbinski,3,2,2,1,3,2.2,"May 6, 2026",,
Cortex,Podcast,Relay FM,3,,,,,3,"January 1, 2024",,https://www.relay.fm/cortex
Star Wars,Movie,,,,,,,,,,
Mystery,Laserdisc,,,,,,,,,,
`;

describe('notion import', () => {
  it('parses both Notion date formats', () => {
    expect(parseNotionDate('October 19, 2026')).toBe('2026-10-19');
    expect(parseNotionDate('2026-10-19')).toBe('2026-10-19');
    expect(parseNotionDate('')).toBeNull();
  });

  it('inserts, then re-imports idempotently, then applies Notion-side changes only', () => {
    const db = openDb(':memory:');
    const first = importCsv(db, csv);
    expect(first.inserted).toBe(4);
    expect(first.skipped).toEqual([{ line: 6, reason: 'unknown type "Laserdisc" for "Mystery"' }]);

    const pantheon = db.select().from(media).all().find((m) => m.title === 'Pantheon')!;
    expect(pantheon.loggedDate).toBe('2022-11-01');
    expect(pantheon.ratingEnjoyability).toBe(4.5);
    expect(pantheon.notionMediaUrl).toContain('imdb');
    const undated = db.select().from(media).all().find((m) => m.title === 'Star Wars')!;
    expect(undated.loggedDate).toBeNull();
    expect(undated.ratingMedium).toBeNull();

    const second = importCsv(db, csv);
    expect(second).toMatchObject({ inserted: 0, updated: 0, unchanged: 4 });

    // A site-only field survives a re-import that changes a Notion-owned one.
    db.update(media).set({ description: 'An animated drama.' }).run();
    const third = importCsv(db, csv.replace('AMC,5,4,4,4.5,5', 'AMC,5,4,4,5,5'));
    expect(third).toMatchObject({ inserted: 0, updated: 1, unchanged: 3 });
    const after = db.select().from(media).all().find((m) => m.title === 'Pantheon')!;
    expect(after.ratingEnjoyability).toBe(5);
    expect(after.description).toBe('An animated drama.');
  });

  it('matches by Notion id when the file carries one, so renames do not duplicate', () => {
    const db = openDb(':memory:');
    const withId = 'Title,Type,Notion ID\nWarfarme,Game,https://app.notion.com/a8e82110185241e5b4f322a9a65c46f7\n';
    importCsv(db, withId);
    const renamed = 'Title,Type,Notion ID\nWarframe,Game,a8e82110-1852-41e5-b4f3-22a9a65c46f7\n';
    expect(importCsv(db, renamed)).toMatchObject({ inserted: 0, updated: 1 });
    expect(db.select().from(media).all().map((m) => m.title)).toEqual(['Warframe']);
  });

  it('keeps the search index in step through the triggers', () => {
    const db = openDb(':memory:');
    importCsv(db, csv);
    expect(searchMedia(db, 'panth').map((h) => h.title)).toEqual(['Pantheon']);
    expect(searchMedia(db, 'relay').map((h) => h.title)).toEqual(['Cortex']);
    expect(searchMedia(db, 'don\'t die').map((h) => h.title)).toEqual(["Good Luck, Have Fun, Don't Die"]);
    expect(searchMedia(db, '')).toEqual([]);
  });
});

describe('notion API sync', () => {
  const row = (title: string, notionId: string, extra: Partial<Parameters<typeof importNotionRows>[1][number]> = {}) => ({
    notionId, title, type: 'Book', creator: null, loggedDate: null,
    ratings: { medium: null, story: null, tone: null, enjoyability: null, effect: null },
    imageUrl: null, mediaUrl: null, ...extra,
  });

  it('adopts existing rows by title, reports new ids and changed fields, and marks rows that stopped coming back', () => {
    const db = openDb(':memory:');
    db.insert(media).values({ title: 'Lent', type: 'Book' }).run();
    const first = importNotionRows(db, [row('Lent', 'aaaa-1'), row('Unsong', 'bbbb-2'), { ...row('Odd', 'cccc-3'), type: 'Laserdisc' }], { complete: true });
    expect(first.inserted).toBe(1);
    expect(first.insertedIds).toHaveLength(1);
    expect(first.updated).toBe(1); // Lent gained its Notion id
    expect(first.skipped[0].reason).toContain('Laserdisc');
    expect(first.missing).toBe(0);
    const lent = db.select().from(media).all().find((m) => m.title === 'Lent')!;
    expect(lent.notionId).toBe('aaaa1');

    const second = importNotionRows(db, [row('Lent', 'aaaa-1', { imageUrl: 'https://x/poster.png' })], { complete: true });
    expect(second.changes).toEqual([{ id: lent.id, fields: ['notionImageUrl'] }]);
    expect(second.missing).toBe(1);
    const unsong = db.select().from(media).all().find((m) => m.title === 'Unsong')!;
    expect(unsong.notionMissingSince).toBeTruthy();

    const third = importNotionRows(db, [row('Lent', 'aaaa-1', { imageUrl: 'https://x/poster.png' }), row('Unsong', 'bbbb-2')], { complete: true });
    expect(third.missing).toBe(0);
    expect(db.select().from(media).all().find((m) => m.title === 'Unsong')!.notionMissingSince).toBeNull();
  });
});
