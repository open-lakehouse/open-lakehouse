// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { requireEnv } from "@/lib/env";
import { codeExecutionEnabled, codeExecutionDisabledResponse } from "@/lib/features";

const JUPYTER_URL = () => process.env.JUPYTER_URL || "http://jupyter:8888";
const JUPYTER_TOKEN = () => requireEnv("JUPYTER_TOKEN");

function validatePath(path: string[]): NextResponse | null {
  const pathStr = path.join("/");
  if (path.some((p) => p.includes("..")) || pathStr.includes("//")) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }
  return null;
}

async function proxy(req: NextRequest, path: string) {
  const baseUrl = JUPYTER_URL();
  const query = req.nextUrl.search;
  const url = `${baseUrl}/api/${path}${query}`;

  const headers: Record<string, string> = {
    Authorization: `token ${JUPYTER_TOKEN()}`,
  };
  if (req.method !== "GET") {
    headers["Content-Type"] = "application/json";
  }

  try {
    const res = await fetch(url, {
      method: req.method,
      headers,
      body: req.method !== "GET" ? await req.text() : undefined,
      signal: AbortSignal.timeout(30000),
    });
    const data = await res.text();
    return new NextResponse(data, {
      status: res.status,
      headers: {
        "Content-Type":
          res.headers.get("Content-Type") || "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Jupyter server unreachable" },
      { status: 502 }
    );
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  const { path } = await params;
  const invalid = validatePath(path);
  if (invalid) return invalid;
  return proxy(req, path.join("/"));
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  const { path } = await params;
  const invalid = validatePath(path);
  if (invalid) return invalid;
  return proxy(req, path.join("/"));
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  const { path } = await params;
  const invalid = validatePath(path);
  if (invalid) return invalid;
  return proxy(req, path.join("/"));
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  const { path } = await params;
  const invalid = validatePath(path);
  if (invalid) return invalid;
  return proxy(req, path.join("/"));
}
