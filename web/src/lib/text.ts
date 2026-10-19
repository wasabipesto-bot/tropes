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
