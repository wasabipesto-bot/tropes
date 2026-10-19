/** URL slug: lowercase ASCII words joined by hyphens. "It/Its Characters" → "it-its-characters". */
export function slugify(name: string): string {
  return name
    .replace(/[ÆÄ]/g, 'ae').replace(/[æä]/g, 'ae').replace(/[ÖØ]/g, 'o').replace(/[öø]/g, 'o').replace(/[Üü]/g, 'u').replace(/ß/g, 'ss').replace(/Œ/g, 'oe').replace(/œ/g, 'oe')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[''’]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}
