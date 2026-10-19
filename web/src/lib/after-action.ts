import type { AstroGlobal } from 'astro';
import { actions } from 'astro:actions';
import { server } from '../actions';

/**
 * Form-posted actions render the same page again. Every action here returns a
 * `returnTo` path; redirect to it so a refresh never resubmits. Returns an
 * error message to show when an action failed.
 */
export function afterAction(Astro: AstroGlobal): { redirect?: Response; error?: string } {
  // `actions` is a proxy, so walk the keys of the server definition instead.
  for (const name of Object.keys(server) as (keyof typeof server)[]) {
    const result = Astro.getActionResult(actions[name]);
    if (!result) continue;
    if (result.error) return { error: result.error.message };
    const to = (result.data as { returnTo?: string } | undefined)?.returnTo;
    if (to && to.startsWith('/')) return { redirect: Astro.redirect(to, 303) };
    return {};
  }
  return {};
}
