/**
 * Tests for the MLflow proxy API route.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

describe("MLflow Proxy (/api/mlflow/[...path])", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.MLFLOW_URL = "http://mlflow:5000";
  });

  it("proxies GET requests to MLflow API", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ experiments: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const mod = await import("@/app/api/mlflow/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/mlflow/2.0/mlflow/experiments/search"
    );
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["2.0", "mlflow", "experiments", "search"] }),
    });

    expect(response.status).toBe(200);

    // Verify the proxied URL goes to /api/2.0/mlflow/experiments/search
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/2.0/mlflow/experiments/search"),
      expect.any(Object)
    );
  });

  it("returns 502 when MLflow is unreachable", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(
      new Error("ECONNREFUSED")
    );

    const mod = await import("@/app/api/mlflow/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/mlflow/2.0/mlflow/experiments/search"
    );
    const response = await mod.GET(req, {
      params: Promise.resolve({ path: ["2.0", "mlflow", "experiments", "search"] }),
    });

    expect(response.status).toBe(502);
    const data = await response.json();
    expect(data.error).toContain("unreachable");
  });

  it("forwards POST body for experiment search", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ experiments: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const mod = await import("@/app/api/mlflow/[...path]/route");
    const body = JSON.stringify({ max_results: 200 });
    const req = new NextRequest(
      "http://localhost:3000/api/mlflow/2.0/mlflow/experiments/search",
      {
        method: "POST",
        body,
        headers: { "Content-Type": "application/json" },
      }
    );

    await mod.POST(req, {
      params: Promise.resolve({ path: ["2.0", "mlflow", "experiments", "search"] }),
    });

    expect(global.fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: "POST",
        body: expect.any(String),
      })
    );
  });

  it("refuses non-search POSTs (experiments/create) with 403", async () => {
    const mod = await import("@/app/api/mlflow/[...path]/route");
    const req = new NextRequest(
      "http://localhost:3000/api/mlflow/2.0/mlflow/experiments/create",
      {
        method: "POST",
        body: JSON.stringify({ name: "evil" }),
        headers: { "Content-Type": "application/json" },
      }
    );
    const response = await mod.POST(req, {
      params: Promise.resolve({ path: ["2.0", "mlflow", "experiments", "create"] }),
    });
    expect(response.status).toBe(403);
    // And it must not have proxied the write upstream.
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("sets Host header for MLflow compatibility", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(
      new Response("OK", {
        status: 200,
        headers: { "Content-Type": "text/plain" },
      })
    );

    const mod = await import("@/app/api/mlflow/[...path]/route");
    const req = new NextRequest("http://localhost:3000/api/mlflow/health");
    await mod.GET(req, {
      params: Promise.resolve({ path: ["health"] }),
    });

    const fetchCall = vi.mocked(global.fetch).mock.calls[0];
    const headers = fetchCall[1]?.headers as Record<string, string>;
    expect(headers.Host).toBe("mlflow:5000");
  });
});
