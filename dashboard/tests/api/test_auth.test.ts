/**
 * Login / logout routes and the middleware gate.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { NextRequest } from "next/server";
import { SESSION_COOKIE, signSession } from "@/lib/session";

function loginReq(body: unknown) {
  return new NextRequest("http://localhost:3000/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/auth/login", () => {
  beforeEach(() => {
    process.env.DASHBOARD_USERNAME = "admin";
    process.env.DASHBOARD_PASSWORD = "s3cret";
    process.env.DASHBOARD_SESSION_SECRET = "unit-test-secret";
  });

  it("sets an httpOnly session cookie on valid credentials", async () => {
    const { POST } = await import("@/app/api/auth/login/route");
    const res = await POST(loginReq({ username: "admin", password: "s3cret" }));
    expect(res.status).toBe(200);
    const cookie = res.cookies.get(SESSION_COOKIE);
    expect(cookie?.value).toBeTruthy();
    expect(cookie?.httpOnly).toBe(true);
  });

  it("rejects a wrong password with 401 and no cookie", async () => {
    const { POST } = await import("@/app/api/auth/login/route");
    const res = await POST(loginReq({ username: "admin", password: "nope" }));
    expect(res.status).toBe(401);
    expect(res.cookies.get(SESSION_COOKIE)).toBeUndefined();
  });

  it("rejects a wrong username", async () => {
    const { POST } = await import("@/app/api/auth/login/route");
    const res = await POST(loginReq({ username: "root", password: "s3cret" }));
    expect(res.status).toBe(401);
  });

  it("returns 400 when fields are missing", async () => {
    const { POST } = await import("@/app/api/auth/login/route");
    const res = await POST(loginReq({ username: "admin" }));
    expect(res.status).toBe(400);
  });

  it("returns 503 when no password is configured", async () => {
    delete process.env.DASHBOARD_PASSWORD;
    const { POST } = await import("@/app/api/auth/login/route");
    const res = await POST(loginReq({ username: "admin", password: "x" }));
    expect(res.status).toBe(503);
  });
});

describe("POST /api/auth/logout", () => {
  it("clears the session cookie", async () => {
    const { POST } = await import("@/app/api/auth/logout/route");
    const res = await POST();
    expect(res.cookies.get(SESSION_COOKIE)?.value).toBe("");
  });
});

describe("middleware", () => {
  beforeEach(() => {
    process.env.DASHBOARD_SESSION_SECRET = "unit-test-secret";
  });

  async function run(path: string, cookie?: string) {
    const { middleware } = await import("@/middleware");
    const req = new NextRequest(`http://localhost:3000${path}`, {
      headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {},
    });
    return middleware(req);
  }

  it("serves the login page at / when signed out", async () => {
    const res = await run("/");
    expect(res.headers.get("location")).toBeNull();
  });

  it("sends a signed-in user from / to /home", async () => {
    const res = await run("/", await signSession("admin"));
    expect(res.headers.get("location")).toBe("http://localhost:3000/home");
  });

  it("redirects pages to the login page with ?next", async () => {
    const res = await run("/catalog?c=unity");
    const loc = new URL(res.headers.get("location") as string);
    expect(loc.pathname).toBe("/");
    expect(loc.searchParams.get("next")).toBe("/catalog?c=unity");
  });

  it("answers 401 for API calls without a session", async () => {
    const res = await run("/api/uc/catalogs");
    expect(res.status).toBe(401);
  });

  it("lets the login endpoint through without a session", async () => {
    const res = await run("/api/auth/login");
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("lets authenticated requests through", async () => {
    const res = await run("/api/uc/catalogs", await signSession("admin"));
    expect(res.status).toBe(200);
  });

  it("rejects a forged cookie", async () => {
    const res = await run("/api/uc/catalogs", await signSession("admin", "wrong-secret"));
    expect(res.status).toBe(401);
  });
});
