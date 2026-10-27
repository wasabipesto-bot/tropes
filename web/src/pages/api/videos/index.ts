import type { APIRoute } from 'astro';
import { z } from 'astro/zod';
import { db } from '../../../db';
import { VIDEO_KINDS, VIDEO_ORIGINS } from '../../../db/schema';
import { upsertVideo } from '../../../lib/videos';
import { badRequest, unauthorized, workerAuthorized } from '../../../lib/worker-auth';

const body = z.object({
  videos: z.array(z.object({
    mediaId: z.number().int().positive(),
    kind: z.enum(VIDEO_KINDS),
    url: z.string().url(),
    label: z.string().default(''),
    origin: z.enum(VIDEO_ORIGINS),
    sourceUrl: z.string().url().nullable().optional(),
    position: z.number().int().min(0).default(0),
  })),
});

/** The worker's openings, endings and title sequences (find_videos). */
export const POST: APIRoute = async ({ request }) => {
  if (!workerAuthorized(db, request)) return unauthorized();
  const parsed = body.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return badRequest(parsed.error.message);
  const counts = { added: 0, kept: 0, updated: 0 };
  db.transaction((tx) => {
    for (const v of parsed.data.videos) counts[upsertVideo(tx as any, v)]++;
  });
  return Response.json(counts);
};
