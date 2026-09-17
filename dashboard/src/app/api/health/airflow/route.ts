// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";

// Liveness probe for the Airflow 3.x API server (bridge address). Airflow is an
// optional service (its own `./lakehouse start airflow`); when it isn't running
// this returns "unknown" and the card renders accordingly.
const AIRFLOW_HEALTH = "http://airflow-webserver:8085/api/v2/monitor/health";

export async function GET() {
  try {
    const res = await fetch(AIRFLOW_HEALTH, { signal: AbortSignal.timeout(3000) });
    return NextResponse.json(
      { status: res.ok ? "healthy" : "unhealthy" },
      { status: res.ok ? 200 : 503 }
    );
  } catch {
    return NextResponse.json({ status: "unknown" }, { status: 503 });
  }
}
