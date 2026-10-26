/**
 * The site's text format: paragraphs separated by blank lines, *italics*,
 * [text](https://…) links, [[Trope name]] links to tropes, and ||spoilers||.
 * Everything is HTML-escaped first; the output is safe to inject.
 */

export interface RenderOptions {
  /** Return the href for a trope name, or null when no such trope exists. */
  tropeHref: (name: string) => string | null;
}

const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function inline(src: string, opts: RenderOptions): string {
  let out = escapeHtml(src);
  // [[Trope name]]
  out = out.replace(/\[\[([^\]\n]+?)\]\]/g, (_, raw: string) => {
    const name = raw.trim();
    const href = opts.tropeHref(name);
    return href ? `<a href="${escapeHtml(href)}" class="tl">${escapeHtml(name)}</a>` : escapeHtml(name);
  });
  // [text](https://url)
  out = out.replace(/\[([^\]\n]+?)\]\((https?:\/\/[^\s)]+)\)/g, (_, text: string, url: string) => `<a href="${url}">${text}</a>`);
  // *italics*
  out = out.replace(/(^|[\s(])\*(\S(?:[^*\n]*?\S)?)\*(?=[\s.,;:!?)]|$)/g, (_, pre: string, text: string) => `${pre}<em>${text}</em>`);
  return out;
}

/** Split on ||…|| and wrap the odd segments as spoilers. */
function spoilers(src: string, opts: RenderOptions): string {
  const parts = src.split('||');
  if (parts.length === 1) return inline(src, opts);
  return parts
    .map((part, i) => {
      if (i % 2 === 0 || !part) return inline(part, opts);
      return `<a href="#spoiler" class="sp" role="button" aria-expanded="false" title="Spoiler. Click to reveal.">${inline(part, opts)}</a>`;
    })
    .join('');
}

/** The text with no markup, for OG descriptions and the API: spoilers become an ellipsis, [[links]] their name. */
export function plainText(src: string, max = 200): string {
  const t = src.replace(/\|\|[^|]*\|\|/g, '…').replace(/\[\[([^\]]+)\]\]/g, '$1').replace(/\s+/g, ' ').trim();
  return t.length > max ? t.slice(0, max - 1).replace(/\s+\S*$/, '') + '…' : t;
}

export function renderInline(src: string, opts: RenderOptions): string {
  return spoilers(src.replace(/\s*\n\s*/g, ' ').trim(), opts);
}

/** Paragraph-level render. Single newlines become spaces; blank lines separate paragraphs. */
export function renderText(src: string, opts: RenderOptions, paragraphAttrs = ''): string {
  return src
    .split(/\n[ \t]*\n/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => `<p${paragraphAttrs}>${renderInline(p, opts)}</p>`)
    .join('\n');
}

/** Trope names referenced as [[links]] in a text, in order of first appearance. */
export function tropeLinksIn(src: string): string[] {
  const seen = new Set<string>();
  for (const m of src.matchAll(/\[\[([^\]\n]+?)\]\]/g)) seen.add(m[1].trim());
  return [...seen];
}

/**
 * A quote's citation, kept short and quiet after the quote: "ch. 17", "S01E03 12:40".
 * Chapter headings copied from a text ("CHAPTER XVII", "Chapter 17: The Fall") become "ch. 17";
 * anything else is shown as written, with shouting headings brought down to title case.
 */
export function formatLocator(locator: string): string {
  const s = locator.trim();
  if (!s) return '';
  if (/^\d{1,4}$/.test(s)) return `ch. ${s}`; // a bare number is a chapter heading copied from the text
  const ch = /^chapter\s+([0-9]+|[ivxlc]+)\b\.?:?\s*(.*)$/i.exec(s);
  if (ch) {
    const n = /^[0-9]+$/.test(ch[1]) ? ch[1] : String(roman(ch[1].toUpperCase()));
    return `ch. ${n}`;
  }
  const letters = s.replace(/[^a-z]/gi, '');
  if (letters.length >= 4 && letters === letters.toUpperCase()) return s.toLowerCase().replace(/(^|\s)(\S)/g, (_, pre: string, c: string) => pre + c.toUpperCase());
  return s;
}

function roman(s: string): number {
  const v: Record<string, number> = { I: 1, V: 5, X: 10, L: 50, C: 100 };
  let total = 0;
  for (let i = 0; i < s.length; i++) {
    const cur = v[s[i]] ?? 0;
    const next = v[s[i + 1]] ?? 0;
    total += cur < next ? -cur : cur;
  }
  return total;
}

/** Seconds from a "12:40" or "1:02:05" stamp, as the subtitle text writes them; null for anything else. */
export function parseStamp(s: string): number | null {
  const m = /^(?:(\d+):)?(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!m) return null;
  return Number(m[1] ?? 0) * 3600 + Number(m[2]) * 60 + Number(m[3]);
}
