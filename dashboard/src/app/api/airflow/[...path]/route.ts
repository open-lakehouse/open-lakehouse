// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { rejectTraversal } from "@/lib/proxy";
import { AirflowAuthError, airflowGet, isAllowedAirflowPath } from "@/lib/airflow";

// READ-ONLY, allow-listed proxy to the Airflow 3.x REST API (v2) for the Jobs page.
// Only GET is exported, so the UI can never trigger, pause, or delete a DAG.
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const bad = rejectTraversal(path);
  if (bad) return bad;
  if (!isAllowedAirflowPath(path)) {
    return NextResponse.json({ error: "Not available through the Jobs proxy" }, { status: 403 });
  }

  const encoded = path.map(encodeURIComponent).join("/");
  try {
    const res = await airflowGet(`${encoded}${req.nextUrl.search}`);
    const data = await res.text();
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
    });
  } catch (err) {
    if (err instanceof AirflowAuthError) {
      return NextResponse.json({ error: err.message, code: "auth" }, { status: 502 });
    }
    return NextResponse.json({ error: "Airflow unreachable" }, { status: 502 });
  }
}
