import type { Media, MediaLink, MediaType } from '../db/schema';

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

export interface Details {
  start?: string; end?: string; seasons?: number; episodes?: number; network?: string; studio?: string; source_material?: string;
  status?: string; runtime_min?: number; director?: string; author?: string; pages?: number; developer?: string; publisher?: string;
  platforms?: string[]; artist?: string; tracks?: number; label?: string; reviews?: { by: string; score: string }[]; posters?: string[];
}

const year = (iso?: string) => (iso && /^\d{4}/.test(iso) ? iso.slice(0, 4) : null);

/** "2022 to 2025", "2022" or null. A run still going shows "since 2022". */
export function yearSpan(d: Details): string | null {
  const a = year(d.start);
  const b = year(d.end);
  if (!a) return null;
  if (b && b !== a) return `${a} to ${b}`;
  if (!b && d.status && /returning|continuing|airing|ongoing/i.test(d.status)) return `since ${a}`;
  return a;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/**
 * "TV series, 2022 to 2025, 2 seasons, 16 episodes. Science fiction, Thriller. Watched November 2022."
 * The middle sentence holds what the lookup found (plan T6); the first and last come from Notion.
 */
export function metadataLine(m: Pick<Media, 'type' | 'label' | 'loggedDate' | 'creator'>, details: Details = {}, genres: string[] = []): string {
  const kind = m.label ? capitalise(m.label) : TYPE_PHRASE[m.type];
  const span = yearSpan(details);
  const first: string[] = [];
  const by = (who?: string | null) => (who ? `${kind} by ${who}` : kind);
  switch (m.type) {
    case 'TV Series':
      first.push(kind);
      if (span) first.push(span);
      if (details.seasons) first.push(plural(details.seasons, 'season'));
      if (details.episodes) first.push(plural(details.episodes, 'episode'));
      if (details.studio) first.push(details.studio);
      break;
    case 'Movie':
      first.push(kind);
      if (span) first.push(span);
      if (details.runtime_min) first.push(details.runtime_min >= 60 ? `${Math.floor(details.runtime_min / 60)} h ${details.runtime_min % 60} min` : `${details.runtime_min} min`);
      if (details.studio && /anime|animation/i.test(genres.join(' '))) first.push(details.studio);
      break;
    case 'Book':
      first.push(by(details.author ?? m.creator));
      if (span) first.push(span);
      break;
    case 'Game':
      first.push(kind);
      if (span) first.push(span);
      if (details.developer ?? m.creator) first.push((details.developer ?? m.creator)!);
      break;
    case 'Album':
      first.push(by(details.artist ?? m.creator));
      if (span) first.push(span);
      if (details.tracks) first.push(plural(details.tracks, 'track'));
      break;
    case 'Podcast':
      first.push(by(details.network ?? m.creator));
      if (span) first.push(span);
      if (details.episodes) first.push(plural(details.episodes, 'episode'));
      break;
    default:
      first.push(by(m.creator));
      if (span) first.push(span);
  }
  const parts = [first.join(', ')];
  if (genres.length) parts.push(genres.join(', '));
  const when = monthYear(m.loggedDate);
  if (when) parts.push(`${VERB[m.type]} ${when}`);
  return parts.map((p) => `${p}.`).join(' ');
}

export const SITE_LABELS: Record<string, string> = {
  wikipedia: 'Wikipedia', imdb: 'IMDb', tmdb: 'TMDB', tvdb: 'TVDB', letterboxd: 'Letterboxd', rt: 'Rotten Tomatoes', metacritic: 'Metacritic',
  mal: 'MyAnimeList', anidb: 'AniDB', ann: 'Anime News Network', steam: 'Steam', goodreads: 'Goodreads', openlibrary: 'Open Library',
  musicbrainz: 'MusicBrainz', spotify: 'Spotify', bandcamp: 'Bandcamp', itunes: 'Apple Podcasts', official: 'Official site',
};

/** Fixed site order per type for the links line (plan T6); anything else follows in this order. */
const SITE_ORDER: Record<string, string[]> = {
  'TV Series': ['wikipedia', 'imdb', 'tvdb', 'tmdb', 'mal', 'anidb', 'ann', 'rt', 'metacritic', 'official'],
  Movie: ['wikipedia', 'imdb', 'tmdb', 'letterboxd', 'rt', 'metacritic', 'mal', 'official'],
  Book: ['wikipedia', 'goodreads', 'openlibrary', 'official'],
  Game: ['wikipedia', 'steam', 'metacritic', 'official'],
  Album: ['wikipedia', 'musicbrainz', 'spotify', 'bandcamp', 'itunes', 'official'],
  Podcast: ['itunes', 'official', 'wikipedia'],
};
const ALL_SITES = Object.keys(SITE_LABELS);

export interface LinkView { site: string; label: string; url: string; score: string | null; hidden: boolean; origin: string; id: number }

/** Links in display order. Hidden ones are kept (the owner's edit form shows them); callers filter. */
export function orderedLinks(type: MediaType, links: MediaLink[]): LinkView[] {
  const order = [...(SITE_ORDER[type] ?? []), ...ALL_SITES];
  const rank = (site: string) => { const i = order.indexOf(site); return i < 0 ? order.length : i; };
  return links
    .slice()
    .sort((a, b) => rank(a.site) - rank(b.site) || a.site.localeCompare(b.site))
    .map((l) => ({ site: l.site, label: SITE_LABELS[l.site] ?? linkLabel(l.url), url: l.url, score: l.score, hidden: l.hidden, origin: l.origin, id: l.id }));
}

/** The site key for a URL the owner pastes, so it slots into the fixed order; null when unknown. */
export function siteOf(url: string): string | null {
  let host: string;
  try { host = new URL(url).hostname.replace(/^www\./, ''); } catch { return null; }
  const table: [RegExp, string][] = [
    [/wikipedia\.org$/, 'wikipedia'], [/imdb\.com$/, 'imdb'], [/themoviedb\.org$/, 'tmdb'], [/thetvdb\.com$/, 'tvdb'], [/letterboxd\.com$/, 'letterboxd'],
    [/rottentomatoes\.com$/, 'rt'], [/metacritic\.com$/, 'metacritic'], [/myanimelist\.net$/, 'mal'], [/anidb\.net$/, 'anidb'], [/animenewsnetwork\.com$/, 'ann'],
    [/steampowered\.com$/, 'steam'], [/goodreads\.com$/, 'goodreads'], [/openlibrary\.org$/, 'openlibrary'], [/musicbrainz\.org$/, 'musicbrainz'],
    [/spotify\.com$/, 'spotify'], [/bandcamp\.com$/, 'bandcamp'], [/apple\.com$/, 'itunes'],
  ];
  for (const [re, site] of table) if (re.test(host)) return site;
  return null;
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
