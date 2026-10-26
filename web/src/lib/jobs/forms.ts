import { z } from 'astro/zod';
import { PROMINENCES } from '../../db/schema';

/**
 * Form input for committing a review. Astro builds the object from the schema's shape: only a
 * plain z.array reads every value of a repeated field (a union reads just the first), and dynamic
 * keys only arrive through a nested object with a catchall, named `prominence.<proposal id>`.
 */
export const commitInput = z.object({
  jobId: z.coerce.number().int().positive(),
  accept: z.array(z.coerce.number().int()).optional(),
  prominence: z.object({}).catchall(z.enum(PROMINENCES)).optional(),
  /** Inline edits, named `who.<proposal id>` and `text.<proposal id>`; a blank field arrives as null. */
  who: z.object({}).catchall(z.string().nullable()).optional(),
  text: z.object({}).catchall(z.string().nullable()).optional(),
});

/** Form input for committing a metadata lookup: accepted confident matches, and a choice per unsure one
 * ("chosen", a candidate index, "none" or "skip"), named `choice.<proposal id>`. */
export const commitMatchesInput = z.object({
  jobId: z.coerce.number().int().positive(),
  accept: z.array(z.coerce.number().int()).optional(),
  choice: z.object({}).catchall(z.string()).optional(),
});
