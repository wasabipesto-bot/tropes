import { openDb } from '../src/db/open';
import { createApiKey } from '../src/lib/worker-auth';

const name = process.argv[2];
if (!name) { console.error('usage: api-key.ts <name>'); process.exit(2); }
console.log(createApiKey(openDb(), name));
