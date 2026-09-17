// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

// Hard server-side cap on a single Jupyter cell execution. A client-supplied
// timeout may only LOWER it; 0, negative, absent, or a value above the cap all
// clamp to the cap, so a runaway cell can't hold the WebSocket + promise open
// indefinitely. Lives in lib/ (not the route) because a Next.js route module may
// only export HTTP handlers.
export const MAX_EXEC_MS = 120_000;

export function cappedTimeout(timeoutMs: number): number {
  return timeoutMs > 0 ? Math.min(timeoutMs, MAX_EXEC_MS) : MAX_EXEC_MS;
}
