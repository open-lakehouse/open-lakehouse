// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { getRunHistory, deleteRun, clearRunHistory } from "@/lib/s3";
import { codeExecutionEnabled, codeExecutionDisabledResponse } from "@/lib/features";

export async function GET() {
  // D6 / T-3.8: run history is part of the disabled pipelines feature.
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  try {
    const history = await getRunHistory();
    return NextResponse.json({ history });
  } catch (err) {
    console.error("GET /api/pipelines/history error:", err);
    return NextResponse.json(
      { error: "Failed to load run history from storage", history: [] },
      { status: 502 }
    );
  }
}

export async function DELETE(req: NextRequest) {
  // D6 / T-3.8: mutating run history is disabled unless code-execution is on.
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  try {
    const { id } = await req.json().catch(() => ({ id: null }));
    if (id) {
      const updated = await deleteRun(id);
      return NextResponse.json({ history: updated });
    }
    await clearRunHistory();
    return NextResponse.json({ history: [] });
  } catch (err) {
    console.error("DELETE /api/pipelines/history error:", err);
    return NextResponse.json(
      { error: "Failed to update run history" },
      { status: 502 }
    );
  }
}
