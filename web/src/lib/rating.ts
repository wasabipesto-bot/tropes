import type { Media } from '../db/schema';

export const AXES = ['medium', 'story', 'tone', 'enjoyability', 'effect'] as const;
export type Axis = (typeof AXES)[number];
export const AXIS_LABELS: Record<Axis, string> = {
  medium: 'Medium',
  story: 'Story',
  tone: 'Tone',
  enjoyability: 'Enjoyability',
  effect: 'Effect',
};
export type Ratings = Record<Axis, number | null>;

export function ratingsOf(m: Pick<Media, 'ratingMedium' | 'ratingStory' | 'ratingTone' | 'ratingEnjoyability' | 'ratingEffect'>): Ratings {
  return {
    medium: m.ratingMedium,
    story: m.ratingStory,
    tone: m.ratingTone,
    enjoyability: m.ratingEnjoyability,
    effect: m.ratingEffect,
  };
}

/** Raw mean of the filled axes, or null when none are filled. */
export function average(r: Ratings): number | null {
  const filled = AXES.map((a) => r[a]).filter((v): v is number => v !== null && v !== undefined);
  if (filled.length === 0) return null;
  return filled.reduce((s, v) => s + v, 0) / filled.length;
}

export function formatAverage(avg: number | null): string {
  return avg === null ? '–' : (Math.round(avg * 10) / 10).toFixed(1);
}

/** "Medium 5, Story 4, …" for the hover title and accessible label; "Not rated" when empty. */
export function breakdown(r: Ratings): string {
  if (average(r) === null) return 'Not rated';
  return AXES.map((a) => `${AXIS_LABELS[a]} ${r[a] === null ? '–' : r[a]}`).join(', ');
}

export function barShade(v: number | null): string {
  if (v === null) return '#E4E3DF';
  if (v >= 4.5) return '#1B1B1B';
  if (v >= 3) return '#7A786F';
  return '#BDBAB1';
}

/** Bar height in px for a score out of 5; a missing axis is a 2px stub. */
export function barHeight(v: number | null, max: number): number {
  if (v === null) return 2;
  return Math.max(2, Math.round((v / 5) * max));
}
