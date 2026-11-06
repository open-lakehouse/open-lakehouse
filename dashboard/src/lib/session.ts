// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

/**
 * Stateless, HMAC-signed session cookie for the platform UI login.
 *
 * Token format: base64url(JSON payload) + "." + base64url(HMAC-SHA256 signature).
 * Uses only Web Crypto so the same code runs in middleware and route handlers.
 *
 * Signing key: DASHBOARD_SESSION_SECRET. When it is unset, instrumentation.ts
 * generates a random one at server start (sessions then end on restart).
 */

export const SESSION_COOKIE = "ol_session";
export const SESSION_TTL_SECONDS = 12 * 60 * 60; // 12h

export interface SessionPayload {
  /** username */
  u: string;
  /** expiry, unix seconds */
  exp: number;
}

const enc = new TextEncoder();
const dec = new TextDecoder();

function b64urlEncode(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(s: string): Uint8Array<ArrayBuffer> {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + pad);
  const out = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function sessionSecret(): string {
  const secret = process.env.DASHBOARD_SESSION_SECRET;
  if (!secret) {
    throw new Error(
      "DASHBOARD_SESSION_SECRET is not set (instrumentation.ts should have generated one)"
    );
  }
  return secret;
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

export async function signSession(
  username: string,
  secret: string = sessionSecret(),
  now: number = Math.floor(Date.now() / 1000)
): Promise<string> {
  const payload: SessionPayload = { u: username, exp: now + SESSION_TTL_SECONDS };
  const body = b64urlEncode(enc.encode(JSON.stringify(payload)));
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(secret), enc.encode(body));
  return `${body}.${b64urlEncode(new Uint8Array(sig))}`;
}

/** Returns the payload when the token is authentic and unexpired, else null. */
export async function verifySession(
  token: string | undefined | null,
  secret: string | undefined = process.env.DASHBOARD_SESSION_SECRET,
  now: number = Math.floor(Date.now() / 1000)
): Promise<SessionPayload | null> {
  if (!token || !secret) return null;
  const parts = token.split(".");
  if (parts.length !== 2) return null;
  const [body, sig] = parts;
  try {
    const ok = await crypto.subtle.verify(
      "HMAC",
      await hmacKey(secret),
      b64urlDecode(sig),
      enc.encode(body)
    );
    if (!ok) return null;
    const payload = JSON.parse(dec.decode(b64urlDecode(body))) as SessionPayload;
    if (typeof payload.u !== "string" || typeof payload.exp !== "number") return null;
    if (payload.exp <= now) return null;
    return payload;
  } catch {
    return null;
  }
}

/** Only allow same-origin relative redirects after login ("/x", never "//x"). */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return "/home";
  }
  if (next === "/") return "/home";
  return next;
}
