// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { rejectTraversal } from "@/lib/proxy";

const MLFLOW_URL = () =>
  process.env.MLFLOW_URL || "http://mlflow-server:5000";

// MLflow exposes its read queries as POST (…/experiments/search, …/runs/search,
// …/registered-models/search, etc.). Allow POST ONLY for those search endpoints
// so the viewer stays read-only — create/log/delete/update POSTs are refused.
const MLFLOW_POST_ALLOWED = /\/search$/;

async function proxy(req: NextRequest, path: string) {
  const baseUrl = MLFLOW_URL();
  const query = req.nextUrl.search;
  const url = `${baseUrl}/api/${path}${query}`;
  const dest = new URL(url);

  const headers: Record<string, string> = {
    Host: dest.host,
    "X-Requested-With": "XMLHttpRequest",
  };
  if (req.method !== "GET") {
    headers["Content-Type"] = "application/json";
  }

  try {
    const res = await fetch(url, {
      method: req.method,
      headers,
      body: req.method !== "GET" ? await req.text() : undefined,
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.text();
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "MLflow unreachable" }, { status: 502 });
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const bad = rejectTraversal(path);
  if (bad) return bad;
  return proxy(req, path.join("/"));
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const bad = rejectTraversal(path);
  if (bad) return bad;
  const joined = path.join("/");
  if (!MLFLOW_POST_ALLOWED.test(joined)) {
    return NextResponse.json(
      { error: "Only MLflow search endpoints are permitted via POST" },
      { status: 403 }
    );
  }
  return proxy(req, joined);
}
