import { describe, expect, it } from 'vitest';
import { editDistance, matchSubject, normTitle, parseExample } from './examples';
import { openDb } from '../db/open';
import { media, series } from '../db/schema';

describe('examples', () => {
  it('splits a bracketed note from the title', () => {
    expect(parseExample('Star Wars: The Empire Strikes Back (Luke)')).toEqual({ title: 'Star Wars: The Empire Strikes Back', note: 'Luke' });
    expect(parseExample('The Fall (2006)')).toEqual({ title: 'The Fall (2006)', note: '' });
    expect(parseExample('Severance')).toEqual({ title: 'Severance', note: '' });
  });

  it('folds case, accents, punctuation and ampersands', () => {
    expect(normTitle("Ocean's Eleven")).toBe('oceans eleven');
    expect(normTitle('Mr. & Mrs. Smith')).toBe('mr and mrs smith');
    expect(normTitle('Pokémon')).toBe('pokemon');
    expect(editDistance('cyberpunk edgerunners', 'cyberpunk edgerunerrs')).toBe(2);
  });

  it('finds works typed loosely', () => {
    const db = openDb(':memory:');
    db.insert(media).values([
      { title: 'Cyberpunk: Edgerunners', type: 'TV Series' },
      { title: 'Cyberpunk 2077', type: 'Game' },
      { title: "Ocean's Eleven", type: 'Movie' },
      { title: 'Star Wars: The Empire Strikes Back', type: 'Movie' },
      { title: 'The Fall', type: 'Movie' },
      { title: 'Fall', type: 'Movie' },
    ]).run();
    db.insert(series).values({ name: 'Friends at the Table', slug: 'friends-at-the-table' }).run();
    expect(matchSubject(db, 'Cyberpunk Edgerunners')?.title).toBe('Cyberpunk: Edgerunners');
    expect(matchSubject(db, 'oceans eleven')?.title).toBe("Ocean's Eleven");
    expect(matchSubject(db, 'Ocean’s Elevn')?.how).toBe('fuzzy');
    expect(matchSubject(db, 'The Empire Strikes Back')?.title).toBe('Star Wars: The Empire Strikes Back');
    expect(matchSubject(db, 'Friends at the Table')?.kind).toBe('series');
    expect(matchSubject(db, 'Cyberpunk')).toBeNull();
    expect(matchSubject(db, 'Fall')?.title).toBe('Fall');
    expect(matchSubject(db, 'Nothing Like This')).toBeNull();
  });
});
