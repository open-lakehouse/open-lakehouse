// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";

// MLflow 3.14 serves the AI Gateway API in the tracking server.
// Probe its endpoint registry so the gateway API and database are both checked.
export async function GET() {
  try {
    const baseUrl = process.env.MLFLOW_URL || "http://mlflow-server:5000";
    const res = await fetch(`${baseUrl}/api/3.0/mlflow/gateway/endpoints/list`, { signal: AbortSignal.timeout(3000) });
    return NextResponse.json(
      { status: res.ok ? "healthy" : "unhealthy" },
      { status: res.ok ? 200 : 503 }
    );
  } catch {
    return NextResponse.json({ status: "unknown" }, { status: 503 });
  }
}
