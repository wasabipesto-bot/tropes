import { randomBytes } from 'node:crypto';
import { generateAuthenticationOptions, generateRegistrationOptions, verifyAuthenticationResponse, verifyRegistrationResponse } from '@simplewebauthn/server';
import type { AuthenticationResponseJSON, RegistrationResponseJSON } from '@simplewebauthn/server';
import { eq, lt } from 'drizzle-orm';
import type { Db } from '../db/open';
import { passkey, webauthnChallenge } from '../db/schema';
import { originFor, rpIdFor } from './config';

/** Passkeys for the one owner (plan Phase 6): registration from the account page, login beside the password. */
const RP_NAME = 'Trope Log';
const USER_ID = new TextEncoder().encode('trope-log-owner');
const CHALLENGE_MINUTES = 5;

function keepChallenge(db: Db, kind: 'register' | 'login', challenge: string): string {
  const id = randomBytes(16).toString('base64url');
  db.delete(webauthnChallenge).where(lt(webauthnChallenge.expiresAt, new Date().toISOString())).run();
  db.insert(webauthnChallenge).values({ id, kind, challenge, expiresAt: new Date(Date.now() + CHALLENGE_MINUTES * 60_000).toISOString() }).run();
  return id;
}

/** The challenge for this id, once; null when unknown, expired or of the other kind. */
function takeChallenge(db: Db, id: string, kind: 'register' | 'login'): string | null {
  const row = db.select().from(webauthnChallenge).where(eq(webauthnChallenge.id, id)).get();
  if (row) db.delete(webauthnChallenge).where(eq(webauthnChallenge.id, id)).run();
  if (!row || row.kind !== kind || row.expiresAt <= new Date().toISOString()) return null;
  return row.challenge;
}

export function listPasskeys(db: Db) {
  return db.select().from(passkey).all();
}

export async function registrationOptions(db: Db, url: URL) {
  const options = await generateRegistrationOptions({
    rpName: RP_NAME,
    rpID: rpIdFor(url),
    userName: 'owner',
    userDisplayName: 'Trope Log owner',
    userID: USER_ID,
    attestationType: 'none',
    excludeCredentials: listPasskeys(db).map((p) => ({ id: p.credentialId, transports: JSON.parse(p.transports) })),
    authenticatorSelection: { residentKey: 'preferred', userVerification: 'preferred' },
  });
  return { options, challengeId: keepChallenge(db, 'register', options.challenge) };
}

export async function finishRegistration(db: Db, url: URL, challengeId: string, response: RegistrationResponseJSON, name: string): Promise<{ ok: true; id: number } | { ok: false; error: string }> {
  const expectedChallenge = takeChallenge(db, challengeId, 'register');
  if (!expectedChallenge) return { ok: false, error: 'The registration took too long; try again.' };
  let verification;
  try {
    verification = await verifyRegistrationResponse({ response, expectedChallenge, expectedOrigin: originFor(url), expectedRPID: rpIdFor(url) });
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
  if (!verification.verified || !verification.registrationInfo) return { ok: false, error: 'The passkey could not be verified.' };
  const c = verification.registrationInfo.credential;
  const row = db
    .insert(passkey)
    .values({ credentialId: c.id, publicKey: Buffer.from(c.publicKey).toString('base64url'), counter: c.counter, transports: JSON.stringify(c.transports ?? []), name: name.trim().slice(0, 60) })
    .returning()
    .get();
  return { ok: true, id: row.id };
}

export async function authenticationOptions(db: Db, url: URL) {
  const options = await generateAuthenticationOptions({
    rpID: rpIdFor(url),
    userVerification: 'preferred',
    allowCredentials: listPasskeys(db).map((p) => ({ id: p.credentialId, transports: JSON.parse(p.transports) })),
  });
  return { options, challengeId: keepChallenge(db, 'login', options.challenge) };
}

export async function finishAuthentication(db: Db, url: URL, challengeId: string, response: AuthenticationResponseJSON): Promise<{ ok: true } | { ok: false; error: string }> {
  const expectedChallenge = takeChallenge(db, challengeId, 'login');
  if (!expectedChallenge) return { ok: false, error: 'The sign-in took too long; try again.' };
  const row = db.select().from(passkey).where(eq(passkey.credentialId, response.id)).get();
  if (!row) return { ok: false, error: 'That passkey is not registered here.' };
  let verification;
  try {
    verification = await verifyAuthenticationResponse({
      response,
      expectedChallenge,
      expectedOrigin: originFor(url),
      expectedRPID: rpIdFor(url),
      credential: { id: row.credentialId, publicKey: new Uint8Array(Buffer.from(row.publicKey, 'base64url')), counter: row.counter, transports: JSON.parse(row.transports) },
    });
  } catch (e) {
    return { ok: false, error: (e as Error).message };
  }
  if (!verification.verified) return { ok: false, error: 'The passkey could not be verified.' };
  db.update(passkey).set({ counter: verification.authenticationInfo.newCounter, lastUsedAt: new Date().toISOString() }).where(eq(passkey.id, row.id)).run();
  return { ok: true };
}
