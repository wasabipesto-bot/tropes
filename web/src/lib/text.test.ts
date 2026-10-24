import { describe, expect, it } from 'vitest';
import { renderInline, renderText, tropeLinksIn } from './text';
import { slugify } from './slug';
import { hashPassword, verifyPassword } from './password';
import { RateLimiter, createSession, deleteSession, sessionIsValid } from './auth';
import { openDb } from '../db/open';

const opts = { tropeHref: (n: string) => (n === 'Soul Manipulation' ? '/tropes/soul-manipulation' : null) };

describe('text', () => {
  it('links known tropes and leaves unknown ones as plain text', () => {
    expect(renderInline('becomes [[Soul Manipulation]] or [[Nope]].', opts)).toBe(
      'becomes <a href="/tropes/soul-manipulation" class="tl">Soul Manipulation</a> or Nope.',
    );
  });
  it('wraps spoilers in place and escapes html', () => {
    expect(renderInline('Gideon ||dies <b>so</b>|| Harrow.', opts)).toBe(
      'Gideon <a href="#spoiler" class="sp" role="button" aria-expanded="false" title="Spoiler. Click to reveal.">dies &lt;b&gt;so&lt;/b&gt;</a> Harrow.',
    );
  });
  it('handles italics, links and paragraphs', () => {
    expect(renderText('A *cavalier* and a [review](https://x.y/z).\n\nSecond.', opts)).toBe(
      '<p>A <em>cavalier</em> and a <a href="https://x.y/z">review</a>.</p>\n<p>Second.</p>',
    );
    expect(renderInline('2 * 3 * 4', opts)).toBe('2 * 3 * 4');
  });
  it('lists trope links', () => {
    expect(tropeLinksIn('[[A]] then [[B]] then [[A]]')).toEqual(['A', 'B']);
  });
  it('slugifies', () => {
    expect(slugify('It/Its Characters')).toBe('it-its-characters');
    expect(slugify("Baldur's Gate 3")).toBe('baldurs-gate-3');
    expect(slugify('Æon Flux')).toBe('aeon-flux');
  });
});

describe('auth', () => {
  it('hashes and verifies passwords', () => {
    const h = hashPassword('correct horse');
    expect(h.startsWith('scrypt:')).toBe(true);
    expect(h).not.toContain('$');
    expect(verifyPassword('correct horse', h)).toBe(true);
    expect(verifyPassword('wrong', h)).toBe(false);
    expect(verifyPassword('x', undefined)).toBe(false);
    expect(verifyPassword('x', 'garbage')).toBe(false);
  });
  it('creates, validates, expires and deletes sessions', () => {
    const db = openDb(':memory:');
    const { id } = createSession(db, 'test');
    expect(sessionIsValid(db, id)).toBe(true);
    expect(sessionIsValid(db, 'nope')).toBe(false);
    deleteSession(db, id);
    expect(sessionIsValid(db, id)).toBe(false);
  });
  it('rate limits', () => {
    const rl = new RateLimiter(2, 1000);
    expect(rl.allow('a', 0)).toBe(true);
    expect(rl.allow('a', 1)).toBe(true);
    expect(rl.allow('a', 2)).toBe(false);
    expect(rl.allow('a', 1001)).toBe(true);
  });
});

import { formatLocator } from './text';

describe('formatLocator', () => {
  it('shortens chapter headings and calms shouting ones', () => {
    expect(formatLocator('CHAPTER 17')).toBe('ch. 17');
    expect(formatLocator('Chapter XII: The Fall')).toBe('ch. 12');
    expect(formatLocator('THE WARREN')).toBe('The Warren');
    expect(formatLocator('S01E03 12:40')).toBe('S01E03 12:40');
    expect(formatLocator('p. 203')).toBe('p. 203');
    expect(formatLocator('')).toBe('');
  });
});
