/**
 * Session cookie signing + redirect sanitising for the platform login.
 */
import { describe, it, expect } from "vitest";
import { signSession, verifySession, safeNextPath, SESSION_TTL_SECONDS } from "@/lib/session";

const SECRET = "test-secret";

describe("session tokens", () => {
  it("round-trips a signed session", async () => {
    const token = await signSession("alice", SECRET, 1000);
    const payload = await verifySession(token, SECRET, 1001);
    expect(payload).toEqual({ u: "alice", exp: 1000 + SESSION_TTL_SECONDS });
  });

  it("rejects a token signed with another secret", async () => {
    const token = await signSession("alice", "other", 1000);
    expect(await verifySession(token, SECRET, 1001)).toBeNull();
  });

  it("rejects a tampered payload", async () => {
    const token = await signSession("alice", SECRET, 1000);
    const [, sig] = token.split(".");
    const forged = Buffer.from(JSON.stringify({ u: "admin", exp: 9e9 })).toString("base64url");
    expect(await verifySession(`${forged}.${sig}`, SECRET, 1001)).toBeNull();
  });

  it("rejects an expired token", async () => {
    const token = await signSession("alice", SECRET, 1000);
    expect(await verifySession(token, SECRET, 1000 + SESSION_TTL_SECONDS)).toBeNull();
  });

  it("rejects garbage and missing secrets", async () => {
    expect(await verifySession("nope", SECRET)).toBeNull();
    expect(await verifySession("a.b.c", SECRET)).toBeNull();
    expect(await verifySession(undefined, SECRET)).toBeNull();
    const token = await signSession("alice", SECRET);
    expect(await verifySession(token, undefined)).toBeNull();
  });
});

describe("safeNextPath", () => {
  it("keeps same-origin relative paths", () => {
    expect(safeNextPath("/catalog?c=unity")).toBe("/catalog?c=unity");
  });
  it("falls back to /home for open-redirect attempts", () => {
    for (const bad of ["//evil.com", "https://evil.com", "/\\evil.com", "", null, "/"]) {
      expect(safeNextPath(bad)).toBe("/home");
    }
  });
});
