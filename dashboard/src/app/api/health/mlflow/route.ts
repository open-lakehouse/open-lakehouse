// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";

export async function GET() {
  const mlflowUrl = process.env.MLFLOW_URL || "http://mlflow-server:5000";
  const url = `${mlflowUrl}/health`;
  const dest = new URL(url);

  try {
    const res = await fetch(url, {
      headers: { Host: dest.host },
      signal: AbortSignal.timeout(3000),
    });
    return NextResponse.json(
      { status: res.ok ? "healthy" : "unhealthy" },
      { status: res.ok ? 200 : 503 }
    );
  } catch {
    return NextResponse.json({ status: "unknown" }, { status: 503 });
  }
}
