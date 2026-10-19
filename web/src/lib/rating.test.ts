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
