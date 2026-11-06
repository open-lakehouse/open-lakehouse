/**
 * Airflow (Jobs) proxy: allow-list, read-only, JWT acquisition and refresh.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";
import { isAllowedAirflowPath, resetAirflowTokenCache } from "@/lib/airflow";

function req(path: string) {
  return new NextRequest(`http://localhost:3000/api/airflow/${path}`);
}

function params(path: string) {
  return { params: Promise.resolve({ path: path.split("?")[0].split("/") }) };
}

describe("isAllowedAirflowPath", () => {
  it("allows the DAG read endpoints the Jobs page uses", () => {
    for (const p of ["dags", "dags/etl", "dags/etl/dagRuns", "dags/~/dagRuns", "dags/etl/tasks", "importErrors", "version"]) {
      expect(isAllowedAirflowPath(p.split("/"))).toBe(true);
    }
  });
  it("refuses endpoints that could expose secrets or config", () => {
    for (const p of ["connections", "variables", "config", "pools", "dags/etl/dagRuns/x/taskInstances", "users"]) {
      expect(isAllowedAirflowPath(p.split("/"))).toBe(false);
    }
  });
});

describe("GET /api/airflow/[...path]", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    resetAirflowTokenCache();
    process.env.AIRFLOW_URL = "http://airflow:8085";
    process.env.AIRFLOW_USERNAME = "admin";
    process.env.AIRFLOW_PASSWORD = "pw";
  });

  it("returns 403 for a non-allow-listed path without calling Airflow", async () => {
    const { GET } = await import("@/app/api/airflow/[...path]/route");
    const res = await GET(req("variables"), params("variables"));
    expect(res.status).toBe(403);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("rejects traversal", async () => {
    const { GET } = await import("@/app/api/airflow/[...path]/route");
    const res = await GET(req("dags/../connections"), params("dags/../connections"));
    expect(res.status).toBe(400);
  });

  it("gets a token, then calls the v2 API with it", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "jwt-1" }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ dags: [], total_entries: 0 }), { status: 200 }));
    const { GET } = await import("@/app/api/airflow/[...path]/route");
    const res = await GET(req("dags?limit=5"), params("dags"));
    expect(res.status).toBe(200);
    const calls = vi.mocked(global.fetch).mock.calls;
    expect(calls[0][0]).toBe("http://airflow:8085/auth/token");
    expect(calls[1][0]).toBe("http://airflow:8085/api/v2/dags?limit=5");
    expect((calls[1][1] as RequestInit).headers).toEqual({ Authorization: "Bearer jwt-1" });
  });

  it("refreshes the token once on 401", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "old" }), { status: 201 }))
      .mockResolvedValueOnce(new Response("expired", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "new" }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ dags: [] }), { status: 200 }));
    const { GET } = await import("@/app/api/airflow/[...path]/route");
    const res = await GET(req("dags"), params("dags"));
    expect(res.status).toBe(200);
    expect(vi.mocked(global.fetch)).toHaveBeenCalledTimes(4);
  });

  it("reports bad credentials as a 502 auth error", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(new Response("no", { status: 401 }));
    const { GET } = await import("@/app/api/airflow/[...path]/route");
    const res = await GET(req("dags"), params("dags"));
    expect(res.status).toBe(502);
    expect((await res.json()).code).toBe("auth");
  });

  it("returns 502 when Airflow is down", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(new Error("ECONNREFUSED"));
    const { GET } = await import("@/app/api/airflow/[...path]/route");
    const res = await GET(req("dags"), params("dags"));
    expect(res.status).toBe(502);
  });

  it("only exports GET (read-only)", async () => {
    const mod = await import("@/app/api/airflow/[...path]/route");
    expect(Object.keys(mod)).toEqual(["GET"]);
  });
});
