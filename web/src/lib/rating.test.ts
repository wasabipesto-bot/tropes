import { describe, expect, it } from 'vitest';
import { average, barHeight, barShade, breakdown, formatAverage } from './rating';

const r = (medium: number | null, story: number | null, tone: number | null, enjoyability: number | null, effect: number | null) => ({ medium, story, tone, enjoyability, effect });

describe('rating', () => {
  it('averages only the filled axes', () => {
    expect(average(r(5, 4, 4, 4.5, 5))).toBe(4.5);
    expect(average(r(3, null, null, null, null))).toBe(3);
    expect(average(r(null, null, null, null, null))).toBeNull();
  });
  it('formats to one decimal with a dash for unrated', () => {
    expect(formatAverage(4.5)).toBe('4.5');
    expect(formatAverage(4.04)).toBe('4.0');
    expect(formatAverage(null)).toBe('–');
  });
  it('writes the breakdown for the hover title', () => {
    expect(breakdown(r(5, 4, 4, 4.5, 5))).toBe('Medium 5, Story 4, Tone 4, Enjoyability 4.5, Effect 5');
    expect(breakdown(r(3, null, null, null, null))).toBe('Medium 3, Story –, Tone –, Enjoyability –, Effect –');
    expect(breakdown(r(null, null, null, null, null))).toBe('Not rated');
  });
  it('shades and sizes bars per the spec', () => {
    expect(barShade(4.5)).toBe('#1B1B1B');
    expect(barShade(3)).toBe('#7A786F');
    expect(barShade(2.5)).toBe('#BDBAB1');
    expect(barShade(null)).toBe('#E4E3DF');
    expect(barHeight(5, 18)).toBe(18);
    expect(barHeight(2.5, 26)).toBe(13);
    expect(barHeight(null, 26)).toBe(2);
  });
});

import { metadataLine, orderedLinks, siteOf, yearSpan } from './media';

describe('metadata line', () => {
  it('builds the per-type middle sentence from the lookup details', () => {
    const tv = { type: 'TV Series' as const, label: null, loggedDate: '2022-11-10', creator: 'AMC' };
    expect(metadataLine(tv, { start: '2022-09-01', end: '2025-02-21', seasons: 2, episodes: 16 }, ['Science fiction', 'Thriller']))
      .toBe('TV series, 2022 to 2025, 2 seasons, 16 episodes. Science fiction, Thriller. Watched November 2022.');
    expect(metadataLine({ type: 'TV Series', label: null, loggedDate: '2026-10-08', creator: null }, { start: '2024-01-11', end: '2024-04-04', episodes: 13, studio: 'Bones' }, ['Action', 'Anime']))
      .toBe('TV series, 2024, 13 episodes, Bones. Action, Anime. Watched October 2026.');
    expect(metadataLine({ type: 'Movie', label: null, loggedDate: null, creator: null }, { start: '2021-09-15', runtime_min: 155 })).toBe('Film, 2021, 2 h 35 min.');
    expect(metadataLine({ type: 'Book', label: null, loggedDate: '2023-03-04', creator: 'Tamsyn Muir' }, { start: '2019-09-10' })).toBe('Book by Tamsyn Muir, 2019. Read March 2023.');
    expect(metadataLine({ type: 'Album', label: null, loggedDate: null, creator: 'Radiohead' }, { start: '1997-05-21', tracks: 12 })).toBe('Album by Radiohead, 1997, 12 tracks.');
    expect(metadataLine({ type: 'Game', label: null, loggedDate: null, creator: 'Remedy' }, { start: '2019', developer: 'Remedy Entertainment' })).toBe('Game, 2019, Remedy Entertainment.');
    expect(metadataLine({ type: 'Book', label: 'web serial', loggedDate: null, creator: 'Scott Alexander' }, {})).toBe('Web serial by Scott Alexander.');
    expect(yearSpan({ start: '2022', status: 'Returning Series' })).toBe('since 2022');
  });

  it('orders links per type and recognises pasted hosts', () => {
    const links = [
      { id: 1, mediaId: 1, site: 'metacritic', url: 'https://www.metacritic.com/tv/pantheon/', score: '77', scoreValue: 77, origin: 'lookup', hidden: false, fetchedAt: '' },
      { id: 2, mediaId: 1, site: 'wikipedia', url: 'https://en.wikipedia.org/wiki/Pantheon', score: null, scoreValue: null, origin: 'lookup', hidden: false, fetchedAt: '' },
      { id: 3, mediaId: 1, site: 'imdb', url: 'https://www.imdb.com/title/tt1/', score: '8.5', scoreValue: 8.5, origin: 'lookup', hidden: true, fetchedAt: '' },
    ] as const;
    expect(orderedLinks('TV Series', [...links] as any).map((l) => `${l.label}${l.score ? ' ' + l.score : ''}`)).toEqual(['Wikipedia', 'IMDb 8.5', 'Metacritic 77']);
    expect(siteOf('https://www.rottentomatoes.com/tv/pantheon')).toBe('rt');
    expect(siteOf('https://example.org/x')).toBeNull();
  });
});
