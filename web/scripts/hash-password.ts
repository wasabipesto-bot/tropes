import { hashPassword } from '../src/lib/password';

const pw = process.argv[2];
if (!pw) {
  console.error('usage: hash-password.ts <password>');
  process.exit(2);
}
console.log(hashPassword(pw));
