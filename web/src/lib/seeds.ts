/** Identity seeds the owner can paste: the same links the lookup reads from Notion, plus Wikipedia and Wikidata. */
export interface Seed { ids: Record<string, string>; qid?: string; wikipedia?: string }

const PATTERNS: [RegExp, (m: RegExpExecArray) => Seed][] = [
  [/imdb\.com\/title\/(tt\d+)/, (m) => ({ ids: { imdb: m[1] } })],
  [/store\.steampowered\.com\/app\/(\d+)/, (m) => ({ ids: { steam: m[1] } })],
  [/goodreads\.com\/book\/show\/(\d+)/, (m) => ({ ids: { goodreads: m[1] } })],
  [/themoviedb\.org\/tv\/(\d+)/, (m) => ({ ids: { tmdb_tv: m[1] } })],
  [/themoviedb\.org\/movie\/(\d+)/, (m) => ({ ids: { tmdb_movie: m[1] } })],
  [/myanimelist\.net\/anime\/(\d+)/, (m) => ({ ids: { mal: m[1] } })],
  [/openlibrary\.org\/works\/(OL\d+W)/, (m) => ({ ids: { openlibrary: m[1] } })],
  [/musicbrainz\.org\/release-group\/([0-9a-f-]{36})/, (m) => ({ ids: { musicbrainz_rg: m[1] } })],
  [/wikidata\.org\/wiki\/(Q\d+)/, (m) => ({ ids: {}, qid: m[1] })],
  [/en\.wikipedia\.org\/wiki\/([^#?]+)/, (m) => ({ ids: {}, wikipedia: decodeURIComponent(m[1]).replace(/_/g, ' ') })],
];

export function seedFromUrl(url: string): Seed | null {
  for (const [re, make] of PATTERNS) {
    const m = re.exec(url);
    if (m) return make(m);
  }
  return null;
}
