// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";

/**
 * D6 / T-3.8 — code-execution + write features (the Pipelines & Notebooks pages,
 * /api/jupyter-exec, /api/pipelines/run, POST /api/pipelines, and
 * DELETE /api/pipelines/history) are DISABLED by default.
 *
 * These endpoints run arbitrary code / mutate state and are only safe behind
 * authentication on a trusted, non-exposed network. Enable them explicitly with
 *   DASHBOARD_ALLOW_CODE_EXECUTION=true
 * (the ./lakehouse start dashboard arm prints a loud warning when it is on).
 */
export function codeExecutionEnabled(): boolean {
  return process.env.DASHBOARD_ALLOW_CODE_EXECUTION === "true";
}

/** Standard 403 body for a route disabled because code-execution is off. */
export function codeExecutionDisabledResponse(): NextResponse {
  return NextResponse.json(
    {
      error: "disabled",
      message:
        "Code-execution features are disabled. Set DASHBOARD_ALLOW_CODE_EXECUTION=true " +
        "(trusted, non-exposed networks only) to enable.",
    },
    { status: 403 }
  );
}
