// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { createHash, timingSafeEqual } from "node:crypto";

/**
 * Platform UI credentials. A single local operator account, configured by
 * DASHBOARD_USERNAME / DASHBOARD_PASSWORD (see docker-compose-dashboard.yml).
 * This gates the UI on a local machine; it is not multi-user identity.
 */
export function configuredUsername(): string {
  return process.env.DASHBOARD_USERNAME || "admin";
}

function digest(s: string): Buffer {
  return createHash("sha256").update(s, "utf8").digest();
}

/** Constant-time check of the submitted credentials. */
export function checkCredentials(username: string, password: string): boolean {
  const expectedPassword = process.env.DASHBOARD_PASSWORD;
  if (!expectedPassword) return false; // refuse logins until a password is set
  const userOk = timingSafeEqual(digest(username), digest(configuredUsername()));
  const passOk = timingSafeEqual(digest(password), digest(expectedPassword));
  return userOk && passOk;
}
