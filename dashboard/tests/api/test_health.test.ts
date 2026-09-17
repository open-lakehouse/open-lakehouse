/**
 * Tests for health check API endpoints.
 * Validates response structure and error handling.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// We test the route handlers by importing them directly.
// The global fetch mock from setup.ts intercepts their upstream calls.

describe("MLflow Health API (/api/health/mlflow)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.MLFLOW_URL = "http://mlflow:5000";
  });

  it("returns healthy when MLflow responds OK", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response("OK", { status: 200 })
    );

    // Dynamic import to get fresh module
    const mod = await import("@/app/api/health/mlflow/route");
    const response = await mod.GET();
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.status).toBe("healthy");
  });

  it("returns unhealthy when MLflow responds with error", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response("Error", { status: 500 })
    );

    const mod = await import("@/app/api/health/mlflow/route");
    const response = await mod.GET();
    const data = await response.json();

    expect(response.status).toBe(503);
    expect(data.status).toBe("unhealthy");
  });

  it("returns unknown when MLflow is unreachable", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(
      new Error("ECONNREFUSED")
    );

    const mod = await import("@/app/api/health/mlflow/route");
    const response = await mod.GET();
    const data = await response.json();

    expect(response.status).toBe(503);
    expect(data.status).toBe("unknown");
  });
});

describe("OpenSharing Health API (/api/health/delta-sharing)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.DELTA_SHARING_URL = "https://delta-sharing:8443";
    process.env.DELTA_SHARING_TOKEN = "test-token";
  });

  it("returns healthy when OpenSharing responds OK", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [] }), { status: 200 })
    );

    const mod = await import("@/app/api/health/delta-sharing/route");
    const response = await mod.GET();
    const data = await response.json();

    expect(data.status).toBe("healthy");
  });

  it("returns unknown on connection error", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(
      new Error("self-signed certificate")
    );

    const mod = await import("@/app/api/health/delta-sharing/route");
    const response = await mod.GET();
    const data = await response.json();

    expect(response.status).toBe(503);
    expect(data.status).toBe("unknown");
  });

  it("returns unconfigured when DELTA_SHARING_TOKEN is not set", async () => {
    delete process.env.DELTA_SHARING_TOKEN;

    const mod = await import("@/app/api/health/delta-sharing/route");
    const response = await mod.GET();
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.status).toBe("unconfigured");
    expect(data.message).toContain("DELTA_SHARING_TOKEN");
  });
});
