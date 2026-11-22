import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { createJupyterSession } from "@/lib/jupyter-session";
vi.mock("@/lib/jupyter-session", () => ({ createJupyterSession: vi.fn() }));
import { POST } from "@/app/api/jupyter-launch/route";

const session = "username-localhost-8889=signed-session; HttpOnly; Path=/";

function request({
  host = "localhost:3000",
  origin = "http://localhost:3000",
  path = "",
  site = "same-origin",
  cookie = "",
} = {}) {
  return new NextRequest(`http://${host}/api/jupyter-launch`, {
    method: "POST",
    headers: {
      host,
      origin,
      "sec-fetch-site": site,
      "Content-Type": "application/x-www-form-urlencoded",
      Cookie: cookie,
    },
    body: new URLSearchParams({ path }),
  });
}

function upstream(status = 200, cookie: string | null = session) {
  return { status, cookies: cookie ? [cookie] : [] };
}

describe("Jupyter browser launch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubEnv("DASHBOARD_ALLOW_CODE_EXECUTION", "false");
    vi.stubEnv("DASHBOARD_ALLOW_JUPYTER_LAUNCH", "true");
    vi.stubEnv("JUPYTER_TOKEN", "test-token");
    vi.stubEnv("JUPYTER_URL", "http://jupyter:8889");
  });
  afterEach(() => vi.unstubAllEnvs());

  it("creates a browser session and redirects without exposing the token", async () => {
    vi.mocked(createJupyterSession).mockResolvedValueOnce(upstream());
    const res = await POST(request());
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("http://localhost:8889/lab");
    expect(res.headers.get("set-cookie")).toBe(`${session}; SameSite=Lax`);
    expect(res.headers.get("cache-control")).toBe("no-store");
    expect(res.headers.get("referrer-policy")).toBe("no-referrer");
    expect(
      Array.from(res.headers.entries()).join(" ") + (await res.text()),
    ).not.toContain("test-token");
    expect(createJupyterSession).toHaveBeenCalledWith(
      new URL("http://jupyter:8889/api/contents?content=0"),
      { Authorization: "token test-token", Host: "localhost:8889" },
    );
  });

  it("preserves notebook paths with spaces and URL characters", async () => {
    vi.mocked(createJupyterSession).mockResolvedValueOnce(upstream());
    const res = await POST(request({ path: "work/a #1?.ipynb" }));
    expect(res.headers.get("location")).toBe(
      "http://localhost:8889/lab/tree/work/a%20%231%3F.ipynb",
    );
  });

  it("matches the browser hostname for 127.0.0.1 sessions", async () => {
    vi.mocked(createJupyterSession).mockResolvedValueOnce(
      upstream(200, session.replace("localhost", "127-0-0-1")),
    );
    const res = await POST(
      request({ host: "127.0.0.1:3000", origin: "http://127.0.0.1:3000" }),
    );
    expect(res.headers.get("location")).toBe("http://127.0.0.1:8889/lab");
  });

  it("reuses an existing Jupyter cookie without forwarding other cookies", async () => {
    vi.mocked(createJupyterSession).mockResolvedValueOnce(upstream(200, null));
    const res = await POST(
      request({ cookie: "other=private; username-localhost-8889=existing" }),
    );
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("http://localhost:8889/lab");
    expect(createJupyterSession).toHaveBeenCalledWith(
      expect.any(URL),
      expect.objectContaining({ Cookie: "username-localhost-8889=existing" }),
    );
  });

  it.each([
    { origin: "http://untrusted.example" },
    { origin: "" },
    { host: "evil.example:3000", origin: "http://evil.example:3000" },
    { site: "cross-site" },
  ])("rejects nonlocal or cross-origin requests %o", async (options) => {
    expect((await POST(request(options))).status).toBe(403);
    expect(createJupyterSession).not.toHaveBeenCalled();
  });

  it.each(["../secret", "/etc/passwd", "work/../secret", "a\\b", "a\u0000b"])(
    "rejects invalid path %s",
    async (path) => {
      expect((await POST(request({ path }))).status).toBe(400);
      expect(createJupyterSession).not.toHaveBeenCalled();
    },
  );

  it("requires opt-in without enabling dashboard execution", async () => {
    vi.stubEnv("DASHBOARD_ALLOW_JUPYTER_LAUNCH", "false");
    const res = await POST(request());
    expect(res.headers.get("location")).toBe(
      "http://localhost:3000/jupyter?error=disabled",
    );
    expect(createJupyterSession).not.toHaveBeenCalled();
  });

  it("allows launch when the existing execution flag is explicitly on", async () => {
    vi.stubEnv("DASHBOARD_ALLOW_JUPYTER_LAUNCH", "false");
    vi.stubEnv("DASHBOARD_ALLOW_CODE_EXECUTION", "true");
    vi.mocked(createJupyterSession).mockResolvedValueOnce(upstream());
    expect((await POST(request())).headers.get("location")).toBe(
      "http://localhost:8889/lab",
    );
  });

  it("shows setup guidance when no token is configured", async () => {
    vi.stubEnv("JUPYTER_TOKEN", "");
    expect((await POST(request())).headers.get("location")).toContain(
      "error=unconfigured",
    );
    expect(createJupyterSession).not.toHaveBeenCalled();
  });

  it.each([401, 403, 500, 302])(
    "handles upstream status %s without following redirects",
    async (status) => {
      vi.mocked(createJupyterSession).mockResolvedValueOnce(
        upstream(status, null),
      );
      const res = await POST(request());
      expect(res.headers.get("location")).toContain(
        status < 500 && status !== 302
          ? "error=credentials"
          : "error=unavailable",
      );
      expect(res.headers.get("set-cookie")).toBeNull();
    },
  );

  it("handles a stopped server without disclosing error details", async () => {
    vi.mocked(createJupyterSession).mockRejectedValueOnce(
      new Error("test-token at http://internal-secret"),
    );
    const res = await POST(request());
    expect(res.headers.get("location")).toContain("error=unavailable");
    expect(await res.text()).not.toContain("test-token");
  });

  it.each([
    null,
    "unrelated=secret; Path=/",
    "username-localhost-8889=unsigned; Path=/",
    `${session}; Domain=localhost`,
  ])("rejects missing or incorrectly scoped login cookies", async (cookie) => {
    vi.mocked(createJupyterSession).mockResolvedValueOnce(
      upstream(200, cookie),
    );
    const res = await POST(request());
    expect(res.headers.get("location")).toContain("error=credentials");
    expect(res.headers.get("set-cookie")).toBeNull();
  });
});
