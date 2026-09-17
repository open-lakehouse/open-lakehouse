// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";

// Liveness probe for the Spark standalone master web UI (bridge address). A 200
// from the UI root means the master is up. Spark is a core service.
const SPARK_MASTER_UI = "http://spark-master-41:8082";

export async function GET() {
  try {
    const res = await fetch(SPARK_MASTER_UI, { signal: AbortSignal.timeout(3000) });
    return NextResponse.json(
      { status: res.ok ? "healthy" : "unhealthy" },
      { status: res.ok ? 200 : 503 }
    );
  } catch {
    return NextResponse.json({ status: "unknown" }, { status: 503 });
  }
}
