// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";

// Liveness probe for the MLflow AI Gateway (deployments server) on the bridge.
// Optional service; returns "unknown" when it isn't running.
const AI_GATEWAY_HEALTH = "http://mlflow-server:5001/health";

export async function GET() {
  try {
    const res = await fetch(AI_GATEWAY_HEALTH, { signal: AbortSignal.timeout(3000) });
    return NextResponse.json(
      { status: res.ok ? "healthy" : "unhealthy" },
      { status: res.ok ? 200 : 503 }
    );
  } catch {
    return NextResponse.json({ status: "unknown" }, { status: 503 });
  }
}
