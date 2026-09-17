// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { rejectTraversal } from "@/lib/proxy";

// Read-only proxy to the S3-compatible object store (SeaweedFS). Renamed from
// /api/minio (CP) to /api/storage since the backing store is no longer MinIO.
const S3_ENDPOINT = () => process.env.S3_ENDPOINT || "http://seaweedfs:8333";

async function proxy(req: NextRequest, path: string) {
  const query = req.nextUrl.search;
  const url = `${S3_ENDPOINT()}/${path}${query}`;

  try {
    const res = await fetch(url, {
      method: req.method,
      signal: AbortSignal.timeout(5000),
    });
    const data = await res.text();
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "text/plain" },
    });
  } catch {
    return NextResponse.json({ error: "Object store unreachable" }, { status: 502 });
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
