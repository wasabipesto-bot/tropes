import { mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { eq } from 'drizzle-orm';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { openDb } from '../db/open';
import { job, media, mediaGenre, mediaLink, proposal } from '../db/schema';
import { afterJobDone } from './jobs/auto';
import { claimJob, completeJob, createJob } from './jobs/queue';
import { posterPath } from './files';
import { commitMatch, markNoMatch, pinCandidate, syncNotionLink, type MatchPayload } from './metadata';

const chosen = { qid: 'Q109639866', label: 'Pantheon', description: 'animated television series', year: 2022, creator: null, kinds: ['animated television series'], ids: { imdb: 'tt11680642' }, wikipedia: 'Pantheon (TV series)', score: 1, reasons: ['seed'], source: 'seed' };
const other = { ...chosen, qid: 'Q188856', label: 'Panthéon', description: 'mausoleum in Paris', year: null, kinds: ['mausoleum'], ids: {}, score: 0.3 };
const payload: MatchPayload = {
  status: 'confident', chosen, candidates: [chosen, other],
  details: { start: '2022-09-01', end: '2025-02-21', seasons: 2, episodes: 16, network: 'Netflix' },
  links: { imdb: { url: 'https://www.imdb.com/title/tt11680642/', score: '8.5', score_value: 8.5 }, rt: { url: 'https://www.rottentomatoes.com/tv/pantheon', score: '100%', score_value: 100 } },
  genres: ['Science fiction', 'Thriller', 'Animation'], ids: { imdb: 'tt11680642', tmdb_tv: '195339' }, extract: 'Pantheon is an animated series.', poster: { source: 'https://theposterdb.com/api/assets/263743' }, notes: [],
};

describe('metadata commit', () => {
  const dir = join(tmpdir(), `tl-meta-${process.pid}-${Date.now()}`);
  const previous = process.env.DATABASE_PATH;
  beforeEach(() => { mkdirSync(dir, { recursive: true }); process.env.DATABASE_PATH = join(dir, 'tropes.db'); });
  afterEach(() => { process.env.DATABASE_PATH = previous; });

  it('pins the identity, writes details, links, genres and the poster, and keeps the owner\'s edits', () => {
    const db = openDb(':memory:');
    const m = db.insert(media).values({ title: 'Pantheon', type: 'TV Series' }).returning().get();
    db.insert(mediaLink).values({ mediaId: m.id, site: 'official', url: 'https://pantheon.example', origin: 'owner' }).run();
    db.insert(mediaLink).values({ mediaId: m.id, site: 'rt', url: 'https://old', origin: 'lookup', hidden: true }).run();
    for (const size of [900, 300, 50] as const) {
      const p = posterPath(m.id, size, true);
      mkdirSync(join(p, '..'), { recursive: true });
      writeFileSync(p, 'RIFFxxxxWEBP');
    }
    commitMatch(db, m.id, payload);
    const row = db.select().from(media).where(eq(media.id, m.id)).get()!;
    expect(row.identity).toBe('pinned');
    expect(row.wikidataId).toBe('Q109639866');
    expect(JSON.parse(row.externalIds)).toMatchObject({ imdb: 'tt11680642', tmdb_tv: '195339' });
    expect(JSON.parse(row.details).episodes).toBe(16);
    expect(JSON.parse(row.identityCandidates)).toHaveLength(1); // runners-up only
    expect(row.posterPath).toBe(String(m.id));
    expect(row.posterSource).toContain('theposterdb');
    expect(existsSync(posterPath(m.id, 300))).toBe(true);
    expect(existsSync(posterPath(m.id, 300, true))).toBe(false);
    const links = db.select().from(mediaLink).where(eq(mediaLink.mediaId, m.id)).all();
    expect(links.map((l) => l.site).sort()).toEqual(['imdb', 'official', 'rt']);
    expect(links.find((l) => l.site === 'rt')!.hidden).toBe(true); // the owner's hide flag survives a refresh
    expect(links.find((l) => l.site === 'rt')!.url).toContain('rottentomatoes');
    expect(db.select().from(mediaGenre).where(eq(mediaGenre.mediaId, m.id)).all().map((g) => g.genre).sort()).toEqual(['Animation', 'Science fiction', 'Thriller']);

    // Edited genres are left alone by a later commit.
    db.update(media).set({ genresEdited: true }).where(eq(media.id, m.id)).run();
    commitMatch(db, m.id, { ...payload, genres: ['Comedy'] });
    expect(db.select().from(mediaGenre).where(eq(mediaGenre.mediaId, m.id)).all()).toHaveLength(3);

    markNoMatch(db, m.id, [other]);
    const none = db.select().from(media).where(eq(media.id, m.id)).get()!;
    expect(none.identity).toBe('none');
    expect(db.select().from(mediaLink).where(eq(mediaLink.mediaId, m.id)).all().map((l) => l.site)).toEqual(['official']);

    pinCandidate(db, m.id, other, [chosen, other]);
    const pinned = db.select().from(media).where(eq(media.id, m.id)).get()!;
    expect(pinned.identity).toBe('pinned');
    expect(pinned.wikidataId).toBe('Q188856');
  });

  it('runs the automatic path: confident matches commit, unsure ones wait, and the dossier build is queued', () => {
    const db = openDb(':memory:');
    const a = db.insert(media).values({ title: 'Pantheon', type: 'TV Series' }).returning().get();
    const b = db.insert(media).values({ title: 'Foreach', type: 'Other' }).returning().get();
    const j = createJob(db, 'lookup_media', { mediaIds: [a.id, b.id], auto: true });
    claimJob(db, ['lookup_media']);
    completeJob(db, j.id, {
      summary: {},
      proposals: [
        { subject: { kind: 'media', id: a.id }, kind: 'match', score: 1, prominence: 'brief', who: '', text: 'Pantheon', evidence: [], seed: false, rejectedBefore: false, flags: [], payload: { ...payload, poster: null } },
        { subject: { kind: 'media', id: b.id }, kind: 'match', score: 0.4, prominence: 'brief', who: '', text: 'No match', evidence: [], seed: false, rejectedBefore: false, flags: [], payload: { ...payload, status: 'check', chosen: other, candidates: [other], poster: null } },
      ],
      dossiers: [], notes: [], verdicts: [], descriptions: [{ mediaId: a.id, text: 'A draft.' }], warnings: [],
    });
    afterJobDone(db, db.select().from(job).where(eq(job.id, j.id)).get()!);
    expect(db.select().from(media).where(eq(media.id, a.id)).get()!.identity).toBe('pinned');
    expect(db.select().from(media).where(eq(media.id, a.id)).get()!.description).toBe('A draft.');
    expect(db.select().from(media).where(eq(media.id, a.id)).get()!.descriptionOrigin).toBe('model');
    expect(db.select().from(media).where(eq(media.id, b.id)).get()!.identity).toBe('check');
    expect(db.select().from(proposal).all().map((p) => p.decision)).toEqual(['accepted', 'pending']);
    const next = db.select().from(job).all().filter((x) => x.id !== j.id);
    expect(next).toHaveLength(1);
    expect(next[0].kind).toBe('build_dossiers');
    expect(JSON.parse(next[0].payload)).toMatchObject({ auto: true, subjects: [{ kind: 'media', id: a.id }, { kind: 'media', id: b.id }] });

    // A model draft never overwrites the owner's description.
    db.update(media).set({ description: 'Mine.', descriptionOrigin: 'owner' }).where(eq(media.id, a.id)).run();
    const j2 = createJob(db, 'write_blurbs', { mediaIds: [a.id] });
    claimJob(db, ['write_blurbs']);
    completeJob(db, j2.id, { summary: {}, proposals: [], dossiers: [], notes: [], verdicts: [], descriptions: [{ mediaId: a.id, text: 'Another draft.' }], warnings: [] });
    expect(db.select().from(media).where(eq(media.id, a.id)).get()!.description).toBe('Mine.');
  });
});

describe('notion media link', () => {
  it('fills its site slot only when the lookup has nothing there, and follows the link', () => {
    const db = openDb(':memory:');
    const m = db.insert(media).values({ title: 'Foreach', type: 'Other', notionMediaUrl: 'https://foreach.neocities.org/' }).returning().get();
    syncNotionLink(db, m.id);
    expect(db.select().from(mediaLink).where(eq(mediaLink.mediaId, m.id)).all()).toMatchObject([{ site: 'official', origin: 'notion' }]);
    // The same link again is not duplicated; a changed link replaces it.
    syncNotionLink(db, m.id);
    expect(db.select().from(mediaLink).where(eq(mediaLink.mediaId, m.id)).all()).toHaveLength(1);
    db.update(media).set({ notionMediaUrl: 'https://www.imdb.com/title/tt1/' }).where(eq(media.id, m.id)).run();
    syncNotionLink(db, m.id);
    expect(db.select().from(mediaLink).where(eq(mediaLink.mediaId, m.id)).all()).toMatchObject([{ site: 'imdb', origin: 'notion' }]);
    // A lookup link for that site wins; the Notion link does not go to "official" when it is the same site.
    db.delete(mediaLink).run();
    db.insert(mediaLink).values({ mediaId: m.id, site: 'imdb', url: 'https://www.imdb.com/title/tt1/', origin: 'lookup' }).run();
    syncNotionLink(db, m.id);
    expect(db.select().from(mediaLink).where(eq(mediaLink.mediaId, m.id)).all()).toHaveLength(1);
    db.update(media).set({ notionMediaUrl: null }).where(eq(media.id, m.id)).run();
    syncNotionLink(db, m.id);
    expect(db.select().from(mediaLink).where(eq(mediaLink.mediaId, m.id)).all().map((l) => l.origin)).toEqual(['lookup']);
  });
});
