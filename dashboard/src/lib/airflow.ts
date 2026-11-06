// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

/**
 * Server-side client for the Airflow 3.x REST API (v2).
 *
 * Airflow 3 issues JWTs from POST /auth/token (username + password, works for both
 * the Simple and FAB auth managers). The token is cached in-process and refreshed
 * on expiry or on a 401. If AIRFLOW_USERNAME / AIRFLOW_PASSWORD are unset the
 * request is sent unauthenticated (fine when Airflow allows anonymous reads).
 */

export const airflowUrl = () => process.env.AIRFLOW_URL || "http://airflow-webserver:8085";

let cached: { token: string; expiresAt: number } | null = null;

/** Exposed for tests. */
export function resetAirflowTokenCache() {
  cached = null;
}

async function fetchToken(): Promise<string | null> {
  const username = process.env.AIRFLOW_USERNAME;
  const password = process.env.AIRFLOW_PASSWORD;
  if (!username || !password) return null;

  const res = await fetch(`${airflowUrl()}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    signal: AbortSignal.timeout(5000),
  });
  if (!res.ok) {
    throw new AirflowAuthError(`Airflow rejected the configured credentials (${res.status})`);
  }
  const data = (await res.json()) as { access_token?: string };
  if (!data.access_token) throw new AirflowAuthError("Airflow returned no access token");
  // Refresh a little early; Airflow's default JWT lifetime is 24h, assume >= 10 min.
  cached = { token: data.access_token, expiresAt: Date.now() + 10 * 60 * 1000 };
  return cached.token;
}

export class AirflowAuthError extends Error {}

async function token(forceRefresh = false): Promise<string | null> {
  if (!forceRefresh && cached && cached.expiresAt > Date.now()) return cached.token;
  return fetchToken();
}

/**
 * GET an Airflow API v2 path (e.g. "dags?limit=100"). Retries once with a fresh
 * token on 401.
 */
export async function airflowGet(pathAndQuery: string): Promise<Response> {
  const url = `${airflowUrl()}/api/v2/${pathAndQuery}`;
  const send = async (t: string | null) =>
    fetch(url, {
      headers: t ? { Authorization: `Bearer ${t}` } : {},
      signal: AbortSignal.timeout(10000),
    });

  let res = await send(await token());
  if (res.status === 401) {
    res = await send(await token(true));
  }
  return res;
}

/**
 * The Jobs page needs only DAG metadata, runs, tasks, and import errors. The proxy
 * refuses everything else (connections, variables, config, ...) so the UI can
 * never be used to read Airflow secrets.
 */
const ALLOWED_PATHS: RegExp[] = [
  /^dags$/,
  /^dags\/[^/]+$/,
  /^dags\/[^/]+\/dagRuns$/,
  /^dags\/[^/]+\/tasks$/,
  /^importErrors$/,
  /^version$/,
];

export function isAllowedAirflowPath(path: string[]): boolean {
  const joined = path.join("/");
  return ALLOWED_PATHS.some((re) => re.test(joined));
}
