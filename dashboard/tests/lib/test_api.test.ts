/**
 * Tests for the frontend API client (src/lib/api.ts).
 * Validates fetchJson error handling, URL construction, and data normalization.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  checkServiceHealth,
  getCatalogs,
  getSchemas,
  getTables,
  getExperiments,
  getShares,
} from "@/lib/api";

describe("checkServiceHealth", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns healthy when service responds OK", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response("OK", { status: 200 })
    );

    const result = await checkServiceHealth(
      "TestService",
      "http://localhost:1234/health",
      1234,
      "Test"
    );

    expect(result.status).toBe("healthy");
    expect(result.name).toBe("TestService");
    expect(result.port).toBe(1234);
  });

  it("returns unhealthy when service responds with error", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response("Error", { status: 503 })
    );

    const result = await checkServiceHealth(
      "TestService",
      "http://localhost:1234/health",
      1234,
      "Test"
    );

    expect(result.status).toBe("unhealthy");
  });

  it("returns unknown when service is unreachable", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(
      new Error("ECONNREFUSED")
    );

    const result = await checkServiceHealth(
      "TestService",
      "http://localhost:1234/health",
      1234,
      "Test"
    );

    expect(result.status).toBe("unknown");
  });
});

describe("getCatalogs", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns catalogs array from response", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ catalogs: [{ id: "1", name: "unity" }] }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const catalogs = await getCatalogs();
    expect(catalogs).toHaveLength(1);
    expect(catalogs[0].name).toBe("unity");
  });

  it("returns empty array when catalogs field is missing", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const catalogs = await getCatalogs();
    expect(catalogs).toEqual([]);
  });

  it("throws on non-OK response", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response("Not Found", { status: 404, statusText: "Not Found" })
    );

    await expect(getCatalogs()).rejects.toThrow("404");
  });
});

describe("getSchemas", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("constructs URL with encoded catalog name", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ schemas: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    await getSchemas("my catalog");

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("catalog_name=my%20catalog")
    );
  });
});

describe("getTables", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("constructs URL with both catalog and schema params", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ tables: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    await getTables("unity", "default");

    const calledUrl = vi.mocked(global.fetch).mock.calls[0][0] as string;
    expect(calledUrl).toContain("catalog_name=unity");
    expect(calledUrl).toContain("schema_name=default");
  });
});

describe("getExperiments", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("sends POST with max_results", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ experiments: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    await getExperiments();

    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/mlflow/"),
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"max_results"'),
      })
    );
  });
});

describe("getShares", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns empty array when items is missing", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const shares = await getShares();
    expect(shares).toEqual([]);
  });
});
