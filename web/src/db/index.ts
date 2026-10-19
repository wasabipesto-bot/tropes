import { openDb } from './open';

/** Process-wide connection. Import this from pages and endpoints. */
export const db = openDb();
