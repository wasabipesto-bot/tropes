/**
 * Passkey round trip against a local Trope Log dev server with Chromium's virtual authenticator:
 * register from /account (as the owner, via a session cookie handed in), log out, sign in with the passkey.
 *   node tropes-passkey.mjs <origin> <sessionCookieValue>
 */
import { chromium } from "playwright";

const [origin, sessionId] = process.argv.slice(2);
if (!origin || !sessionId) { console.error("usage: node tropes-passkey.mjs <origin> <sessionCookieValue>"); process.exit(2); }
const host = new URL(origin).hostname;
const browser = await chromium.launch({ args: ["--no-sandbox"] });
const context = await browser.newContext();
const page = await context.newPage();
const logs = [];
page.on("console", (m) => logs.push(`[${m.type()}] ${m.text()}`));
page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));
page.on("response", (r) => { if (r.status() >= 400) logs.push(`[http ${r.status()}] ${r.url()}`); });

const cdp = await context.newCDPSession(page);
await cdp.send("WebAuthn.enable");
const { authenticatorId } = await cdp.send("WebAuthn.addVirtualAuthenticator", {
  options: { protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true },
});

// 1. Register as the owner.
await context.addCookies([{ name: "tl_session", value: sessionId, domain: host, path: "/" }]);
await page.goto(`${origin}/account`, { waitUntil: "networkidle" });
await page.fill("#pk-name", "virtual test key");
await page.click("#add-passkey button[type=submit]");
await page.waitForFunction(() => document.body.innerText.includes("virtual test key") && document.body.innerText.includes("added"), null, { timeout: 20000 }).catch(() => {});
const afterRegister = await page.evaluate(() => ({ status: document.getElementById("pk-status")?.textContent, body: document.body.innerText.slice(0, 600) }));
const creds = await cdp.send("WebAuthn.getCredentials", { authenticatorId });
console.log("registered:", afterRegister.body.includes("virtual test key") && afterRegister.body.includes("added") ? "yes" : "NO", "| authenticator holds", creds.credentials.length, "credential(s)", afterRegister.status ? `| status: ${afterRegister.status}` : "");

// 2. Log out (drop the cookie) and sign in with the passkey.
await context.clearCookies();
await page.goto(`${origin}/login`, { waitUntil: "networkidle" });
const hasButton = await page.$("#use-passkey");
console.log("login page offers a passkey button:", hasButton ? "yes" : "NO");
if (hasButton) {
  await page.click("#use-passkey");
  await page.waitForURL((u) => u.pathname === "/tropes", { timeout: 20000 }).catch(() => {});
  const url = page.url();
  const owner = await page.evaluate(() => document.body.innerText.includes("Log out"));
  const status = await page.evaluate(() => document.getElementById("pk-status")?.textContent ?? "");
  console.log("signed in with the passkey:", url.endsWith("/tropes") && owner ? "yes" : "NO", "| landed on", url, status ? `| status: ${status}` : "");
}
await page.screenshot({ path: "/out/passkey.png", fullPage: false }).catch(() => {});
console.log(logs.filter((l) => !l.includes("[vite]")).slice(0, 12).join("\n"));
await browser.close();
