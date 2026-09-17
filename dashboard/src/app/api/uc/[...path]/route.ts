// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { rejectTraversal } from "@/lib/proxy";

// READ-ONLY proxy to the Unity Catalog REST API. The viewer only needs GET, so
// only GET is exported — mutating verbs (POST/PUT/PATCH/DELETE) are not handled
// and Next returns 405. This means the proxy can never write to UC, even when
// code-execution is enabled.
const UC_URL = () => process.env.UNITY_CATALOG_URL || "http://unity-catalog:8080";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const bad = rejectTraversal(path);
  if (bad) return bad;

  const url = `${UC_URL()}/api/2.1/unity-catalog/${path.join("/")}${req.nextUrl.search}`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
    const data = await res.text();
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "Unity Catalog unreachable" }, { status: 502 });
  }
}
