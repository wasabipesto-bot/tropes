import type { Db } from '../db/open';
import type { InstanceView } from './queries';

/** The public read API's shape for an instance: what the pages show, as JSON, spoilers still in ||bars||. */
export function instanceJson(v: InstanceView) {
  return {
    id: v.inst.id,
    trope: { id: v.trope.id, name: v.trope.name, slug: v.trope.slug, url: `/tropes/${v.trope.slug}` },
    subject: { kind: v.inst.subjectKind, id: v.inst.subjectId, title: v.subject.title, url: v.subject.href },
    viaSeries: v.viaSeries ? { id: v.viaSeries.id, name: v.viaSeries.name, slug: v.viaSeries.slug } : null,
    who: v.inst.who,
    text: v.inst.text,
    prominence: v.inst.prominence,
    verified: v.inst.verified,
    notable: v.notable,
    evidence: v.evidence.map((e) => ({ kind: e.kind, content: e.content, locator: e.locator, url: e.filePath ? `/evidence/${e.filePath}` : null })),
  };
}

export function apiJson(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'public, max-age=300', 'access-control-allow-origin': '*' },
  });
}

export type { Db };
