// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";

/**
 * Shared path-traversal guard for the `[...path]` proxy routes. Rejects any
 * segment containing `..` or a `//` sequence, so a client cannot normalize the
 * proxied URL outside the intended prefix (e.g. `/api/storage/a/../../x`).
 * Returns a 400 response to short-circuit, or null when the path is safe.
 */
export function rejectTraversal(path: string[]): NextResponse | null {
  const joined = path.join("/");
  if (path.some((p) => p.includes("..")) || joined.includes("//")) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }
  return null;
}
