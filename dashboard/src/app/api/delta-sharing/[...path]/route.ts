// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";

const DS_URL = () =>
  process.env.DELTA_SHARING_URL || "https://delta-sharing:8443";

async function proxy(req: NextRequest, path: string) {
  // Delta Sharing is an optional, separately-started service. When it isn't
  // configured (no token), degrade gracefully rather than throwing a 500 so the
  // Sharing page can render an "unconfigured" empty state.
  const token = process.env.DELTA_SHARING_TOKEN;
  if (!token) {
    return NextResponse.json(
      { items: [], status: "unconfigured" },
      { status: 503 }
    );
  }

  const url = `${DS_URL()}/delta-sharing/${path}${req.nextUrl.search}`;
  try {
    const res = await fetch(url, {
      method: req.method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      signal: AbortSignal.timeout(5000),
      // Self-signed dev cert: TLS verification is disabled process-wide via
      // NODE_TLS_REJECT_UNAUTHORIZED=0 (docker-compose-dashboard.yml). Node's
      // fetch ignores a per-request rejectUnauthorized option, so don't set one.
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
      { error: "Delta Sharing server unreachable" },
      { status: 502 }
    );
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(req, path.join("/"));
}
