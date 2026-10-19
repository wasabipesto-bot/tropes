/** Minimal RFC 4180 parser: quoted fields, doubled quotes, CRLF or LF, embedded newlines. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let i = 0;
  let quoted = false;
  if (text.charCodeAt(0) === 0xfeff) i = 1; // BOM
  while (i < text.length) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        quoted = false; i++; continue;
      }
      field += c; i++; continue;
    }
    if (c === '"') { quoted = true; i++; continue; }
    if (c === ',') { row.push(field); field = ''; i++; continue; }
    if (c === '\r') { i++; continue; }
    if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; i++; continue; }
    field += c; i++;
  }
  if (field !== '' || row.length > 0) { row.push(field); rows.push(row); }
  return rows.filter((r) => !(r.length === 1 && r[0] === ''));
}

/** Rows as objects keyed by the header row. */
export function parseCsvRecords(text: string): Record<string, string>[] {
  const [header, ...body] = parseCsv(text);
  if (!header) return [];
  return body.map((r) => Object.fromEntries(header.map((h, j) => [h.trim(), r[j] ?? ''])));
}
