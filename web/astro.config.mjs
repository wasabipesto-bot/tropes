// @ts-check
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';

export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  // better-sqlite3 is a native addon; keep it out of the SSR bundle.
  vite: { ssr: { external: ['better-sqlite3'] } },
});
