/** A consistent copy of the live database while the site runs: npx tsx scripts/snapshot.ts <src.db> <dst.sqlite> */
import Database from 'better-sqlite3';

const [src, dst] = process.argv.slice(2);
if (!src || !dst) {
  console.error('usage: snapshot.ts <src.db> <dst.sqlite>');
  process.exit(2);
}
const db = new Database(src, { readonly: true });
db.exec(`VACUUM INTO '${dst.replace(/'/g, "''")}'`);
db.close();
console.log(`snapshot ${dst}`);
