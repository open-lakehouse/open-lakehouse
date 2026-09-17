// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";

export async function GET() {
  const dsUrl =
    process.env.DELTA_SHARING_URL || "https://delta-sharing:8443";
  const token = process.env.DELTA_SHARING_TOKEN;

  if (!token) {
    return NextResponse.json({
      status: "unconfigured",
      message: "DELTA_SHARING_TOKEN not set",
    });
  }

  try {
    const res = await fetch(`${dsUrl}/delta-sharing/shares`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(3000),
      // Self-signed dev cert handled process-wide via NODE_TLS_REJECT_UNAUTHORIZED=0
      // (Node's fetch ignores a per-request rejectUnauthorized option).
    });
    return NextResponse.json({ status: res.ok ? "healthy" : "unhealthy" });
  } catch {
    return NextResponse.json({ status: "unknown" }, { status: 503 });
  }
}
