/**
 * Tests for the Jupyter proxy API route path traversal protection.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

describe("Jupyter Proxy (/api/jupyter/[...path])", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.JUPYTER_URL = "http://jupyter:8888";
    process.env.JUPYTER_TOKEN = "test-token";
  });

  it("rejects path with .. segment", async () => {
    const mod = await import("@/app/api/jupyter/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/jupyter/contents/..%2F..%2Fetc/passwd"
    );
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["contents", "..", "..", "etc", "passwd"] }),
    });

    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.error).toBe("Invalid path");
  });

  it("rejects path with // (double slash)", async () => {
    const mod = await import("@/app/api/jupyter/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/jupyter/contents//etc/passwd"
    );
    // Next.js catch-all routes can produce empty segments from double slashes
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["contents", "", "etc", "passwd"] }),
    });

    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.error).toBe("Invalid path");
  });

  it("rejects path traversal in POST requests", async () => {
    const mod = await import("@/app/api/jupyter/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/jupyter/contents/../secret",
      { method: "POST", body: "{}" }
    );
    const response = await mod.POST(req, {
      params: Promise.resolve({ path: ["contents", "..", "secret"] }),
    });

    expect(response.status).toBe(400);
  });

  it("rejects path traversal in PATCH requests", async () => {
    const mod = await import("@/app/api/jupyter/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/jupyter/contents/../secret",
      { method: "PATCH", body: "{}" }
    );
    const response = await mod.PATCH(req, {
      params: Promise.resolve({ path: ["contents", "..", "secret"] }),
    });

    expect(response.status).toBe(400);
  });

  it("rejects path traversal in DELETE requests", async () => {
    const mod = await import("@/app/api/jupyter/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/jupyter/contents/../secret",
      { method: "DELETE" }
    );
    const response = await mod.DELETE(req, {
      params: Promise.resolve({ path: ["contents", "..", "secret"] }),
    });

    expect(response.status).toBe(400);
  });

  it("allows normal paths like contents/work", async () => {
    const mockResponse = JSON.stringify({ content: [], type: "directory" });
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(mockResponse, {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const mod = await import("@/app/api/jupyter/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/jupyter/contents/work"
    );
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["contents", "work"] }),
    });

    expect(response.status).toBe(200);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/contents/work"),
      expect.any(Object)
    );
  });

  it("returns 502 when Jupyter is unreachable", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(
      new Error("ECONNREFUSED")
    );

    const mod = await import("@/app/api/jupyter/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/jupyter/contents/work"
    );
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["contents", "work"] }),
    });

    expect(response.status).toBe(502);
    const data = await response.json();
    expect(data.error).toContain("unreachable");
  });
});
