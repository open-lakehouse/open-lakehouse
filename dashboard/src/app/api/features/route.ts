// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";
import { codeExecutionEnabled } from "@/lib/features";

// Read-only: lets the client (sidebar nav, page guards) discover whether the
// code-execution features are enabled without exposing any other server config.
export async function GET() {
  return NextResponse.json({ codeExecution: codeExecutionEnabled() });
}
