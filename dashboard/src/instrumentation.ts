// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

/**
 * Runs once at server start. If no DASHBOARD_SESSION_SECRET was provided, mint a
 * random one so session cookies are never signed with a guessable key. Sessions
 * then last only until the dashboard restarts — set the variable to persist them.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  if (!process.env.DASHBOARD_SESSION_SECRET) {
    const { randomBytes } = await import("node:crypto");
    process.env.DASHBOARD_SESSION_SECRET = randomBytes(32).toString("hex");
  }
}
