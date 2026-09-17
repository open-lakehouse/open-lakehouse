// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

/**
 * Require an environment variable to be set.
 * Throws with a clear error message if missing.
 */
export function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing required environment variable: ${name}. ` +
      `Ensure it is set in your .env file or docker-compose.yml.`
    );
  }
  return value;
}
