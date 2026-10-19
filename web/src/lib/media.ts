import type { Media, MediaType } from '../db/schema';

/** Short type label shown next to titles: the override if set, else "TV" for TV Series, else the type. */
export function typeLabel(m: Pick<Media, 'type' | 'label'>): string {
  if (m.label) return m.label;
  return m.type === 'TV Series' ? 'TV' : m.type;
}

const TYPE_PHRASE: Record<MediaType, string> = {
  Book: 'Book',
  'TV Series': 'TV series',
  Movie: 'Film',
  Game: 'Game',
  Podcast: 'Podcast',
  Album: 'Album',
  Other: 'Other',
};

const VERB: Record<MediaType, string> = {
  Book: 'Read',
  'TV Series': 'Watched',
  Movie: 'Watched',
  Game: 'Played',
  Podcast: 'Listened',
  Album: 'Listened',
  Other: 'Logged',
};

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export function monthYear(iso: string | null): string | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  if (!m) return null;
  return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

/** "TV series. Watched November 2022." The middle part (years, episodes, genres) arrives with external metadata in Phase 4. */
export function metadataLine(m: Pick<Media, 'type' | 'label' | 'loggedDate' | 'creator'>): string {
  const kind = m.label ? capitalise(m.label) : TYPE_PHRASE[m.type];
  const parts = [m.creator ? `${kind} by ${m.creator}` : kind];
  const when = monthYear(m.loggedDate);
  if (when) parts.push(`${VERB[m.type]} ${when}`);
  return parts.map((p) => `${p}.`).join(' ');
}

function capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const HOST_LABELS: [RegExp, string][] = [
  [/(^|\.)imdb\.com$/, 'IMDb'],
  [/(^|\.)goodreads\.com$/, 'Goodreads'],
  [/(^|\.)steampowered\.com$/, 'Steam'],
  [/(^|\.)spotify\.com$/, 'Spotify'],
  [/(^|\.)wikipedia\.org$/, 'Wikipedia'],
  [/(^|\.)myanimelist\.net$/, 'MyAnimeList'],
  [/(^|\.)letterboxd\.com$/, 'Letterboxd'],
  [/(^|\.)thetvdb\.com$/, 'TVDB'],
  [/(^|\.)themoviedb\.org$/, 'TMDB'],
  [/(^|\.)metacritic\.com$/, 'Metacritic'],
  [/(^|\.)rottentomatoes\.com$/, 'Rotten Tomatoes'],
  [/(^|\.)anidb\.net$/, 'AniDB'],
  [/(^|\.)animenewsnetwork\.com$/, 'Anime News Network'],
  [/(^|\.)bandcamp\.com$/, 'Bandcamp'],
  [/(^|\.)youtube\.com$/, 'YouTube'],
  [/(^|\.)relay\.fm$/, 'Relay FM'],
];

/** Human label for an external link, by host. Falls back to the bare hostname. */
export function linkLabel(url: string): string {
  let host: string;
  try {
    host = new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
  for (const [re, label] of HOST_LABELS) if (re.test(host)) return label;
  return host;
}
