/**
 * Tests for the Unity Catalog proxy API route.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

describe("UC Proxy (/api/uc/[...path])", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.UNITY_CATALOG_URL = "http://unity-catalog:8080";
  });

  it("proxies GET requests to Unity Catalog", async () => {
    const mockResponse = JSON.stringify({ catalogs: [{ name: "unity" }] });
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(mockResponse, {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const mod = await import("@/app/api/uc/[...path]/route");
    const req = new NextRequest("http://localhost:3000/api/uc/catalogs");
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["catalogs"] }),
    });

    expect(response.status).toBe(200);
    const data = JSON.parse(await response.text());
    expect(data.catalogs).toHaveLength(1);

    // Verify the proxied URL
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/2.1/unity-catalog/catalogs"),
      expect.any(Object)
    );
  });

  it("returns 502 when Unity Catalog is unreachable", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(
      new Error("ECONNREFUSED")
    );

    const mod = await import("@/app/api/uc/[...path]/route");
    const req = new NextRequest("http://localhost:3000/api/uc/catalogs");
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["catalogs"] }),
    });

    expect(response.status).toBe(502);
    const data = await response.json();
    expect(data.error).toContain("unreachable");
  });

  it("passes query parameters through to upstream", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ schemas: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const mod = await import("@/app/api/uc/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/uc/schemas?catalog_name=unity"
    );
    await mod.GET(req, {
      params: Promise.resolve({ path: ["schemas"] }),
    });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("?catalog_name=unity"),
      expect.any(Object)
    );
  });

  it("is read-only: does not export a mutating POST handler", async () => {
    // The viewer never writes to UC. With no POST export Next returns 405, so
    // there is no unauthenticated mutating proxy even with the flag off.
    const mod = await import("@/app/api/uc/[...path]/route");
    expect(
      (mod as Record<string, unknown>).POST ??
        (mod as Record<string, unknown>).PUT ??
        (mod as Record<string, unknown>).PATCH ??
        (mod as Record<string, unknown>).DELETE
    ).toBeUndefined();
  });

  it("rejects path traversal (400)", async () => {
    const mod = await import("@/app/api/uc/[...path]/route");
    const req = new NextRequest("http://localhost:3000/api/uc/a/x");
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["a", "..", "..", "x"] }),
    });
    expect(response.status).toBe(400);
  });
});
