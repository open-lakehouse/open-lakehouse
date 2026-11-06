// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

export interface ServiceHealth {
  name: string;
  status: "healthy" | "unhealthy" | "unknown";
  url: string;
  port: number;
  description: string;
}

export interface Catalog {
  id: string;
  name: string;
  comment?: string;
  owner?: string;
  created_at?: number;
  updated_at?: number;
  properties?: Record<string, string>;
}

export interface Schema {
  name: string;
  catalog_name: string;
  full_name?: string;
  comment?: string;
  owner?: string;
  created_at?: number;
  updated_at?: number;
  properties?: Record<string, string>;
}

export interface Table {
  name: string;
  catalog_name: string;
  schema_name: string;
  table_type: string;
  table_id?: string;
  comment?: string;
  owner?: string;
  data_source_format?: string;
  storage_location?: string;
  columns?: Column[];
  properties?: Record<string, string>;
  created_at?: number;
  updated_at?: number;
}

export interface Column {
  name: string;
  type_name: string;
  type_text: string;
  position: number;
  nullable: boolean;
  comment?: string;
}

export interface MlflowExperiment {
  experiment_id: string;
  name: string;
  artifact_location: string;
  lifecycle_stage: string;
  creation_time?: number;
  last_update_time?: number;
}

export interface MlflowRun {
  info: {
    run_id: string;
    experiment_id: string;
    status: string;
    start_time: number;
    end_time?: number;
    artifact_uri: string;
    run_name?: string;
  };
  data: {
    metrics?: { key: string; value: number; timestamp: number }[];
    params?: { key: string; value: string }[];
    tags?: { key: string; value: string }[];
  };
}

export interface DeltaShare {
  name: string;
  id?: string;
}

export interface DeltaShareSchema {
  name: string;
  share: string;
}

export interface DeltaShareTable {
  name: string;
  schema: string;
  share: string;
  id?: string;
}

/** Session expired mid-use: send the browser back to the login page. */
function handleUnauthenticated(res: Response) {
  if (res.status === 401 && typeof window !== "undefined") {
    const next = window.location.pathname + window.location.search;
    window.location.assign(`/?next=${encodeURIComponent(next)}`);
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    handleUnauthenticated(res);
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.error) message = body.detail ? `${body.error}: ${body.detail}` : body.error;
      else if (body?.detail) message = String(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
  return res.json();
}

export async function checkServiceHealth(
  name: string,
  url: string,
  port: number,
  description: string
): Promise<ServiceHealth> {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
    return { name, status: res.ok ? "healthy" : "unhealthy", url, port, description };
  } catch {
    return { name, status: "unknown", url, port, description };
  }
}

export async function getCatalogs(): Promise<Catalog[]> {
  const data = await fetchJson<{ catalogs: Catalog[] }>("/api/uc/catalogs");
  return data.catalogs ?? [];
}

export async function getSchemas(catalog: string): Promise<Schema[]> {
  const data = await fetchJson<{ schemas: Schema[] }>(
    `/api/uc/schemas?catalog_name=${encodeURIComponent(catalog)}`
  );
  return data.schemas ?? [];
}

export async function getTables(catalog: string, schema: string): Promise<Table[]> {
  const data = await fetchJson<{ tables: Table[] }>(
    `/api/uc/tables?catalog_name=${encodeURIComponent(catalog)}&schema_name=${encodeURIComponent(schema)}`
  );
  return data.tables ?? [];
}

export async function getTable(fullName: string): Promise<Table> {
  return fetchJson<Table>(`/api/uc/tables/${encodeURIComponent(fullName)}`);
}

export async function getExperiments(): Promise<MlflowExperiment[]> {
  const res = await fetch("/api/mlflow/2.0/mlflow/experiments/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_results: 200 }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const data = await res.json();
  return data.experiments ?? [];
}

export async function getExperimentRuns(experimentId: string): Promise<MlflowRun[]> {
  const res = await fetch("/api/mlflow/2.0/mlflow/runs/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ experiment_ids: [experimentId], max_results: 100 }),
  });
  if (!res.ok) throw new Error(`${res.status}`);
  const data = await res.json();
  return data.runs ?? [];
}

export async function getShares(): Promise<DeltaShare[]> {
  const data = await fetchJson<{ items: DeltaShare[] }>("/api/delta-sharing/shares");
  return data.items ?? [];
}

export async function getShareSchemas(share: string): Promise<DeltaShareSchema[]> {
  const data = await fetchJson<{ items: DeltaShareSchema[] }>(
    `/api/delta-sharing/shares/${encodeURIComponent(share)}/schemas`
  );
  return data.items ?? [];
}

export async function getShareTables(
  share: string,
  schema: string
): Promise<DeltaShareTable[]> {
  const data = await fetchJson<{ items: DeltaShareTable[] }>(
    `/api/delta-sharing/shares/${encodeURIComponent(share)}/schemas/${encodeURIComponent(schema)}/tables`
  );
  return data.items ?? [];
}

// --- Jupyter Notebook API ---

export interface JupyterContentItem {
  name: string;
  path: string;
  type: "notebook" | "file" | "directory";
  last_modified: string;
  size?: number;
  content?: JupyterContentItem[] | JupyterNotebook;
  format?: string;
}

export interface JupyterNotebook {
  cells: JupyterCell[];
  metadata: Record<string, unknown>;
  nbformat: number;
  nbformat_minor: number;
}

export interface JupyterCell {
  cell_type: "code" | "markdown" | "raw";
  source: string | string[];
  metadata: Record<string, unknown>;
  outputs?: JupyterCellOutput[];
  execution_count?: number | null;
}

export interface JupyterCellOutput {
  output_type: "stream" | "execute_result" | "display_data" | "error";
  text?: string[];
  data?: Record<string, unknown>;
  name?: string;
  ename?: string;
  evalue?: string;
  traceback?: string[];
}

export interface JupyterKernel {
  id: string;
  name: string;
  execution_state: string;
  last_activity: string;
}

export interface JupyterSession {
  id: string;
  path: string;
  name: string;
  type: string;
  kernel: JupyterKernel;
}

export async function getNotebooks(dirPath = "work"): Promise<JupyterContentItem[]> {
  const data = await fetchJson<JupyterContentItem>(
    `/api/jupyter/contents/${encodeURIComponent(dirPath)}?content=1`
  );
  if (data.type === "directory" && Array.isArray(data.content)) {
    return data.content.filter(
      (item) => item.type === "notebook" || item.type === "directory"
    );
  }
  return [];
}

export async function getNotebookContent(
  path: string
): Promise<JupyterContentItem> {
  return fetchJson<JupyterContentItem>(
    `/api/jupyter/contents/${encodeURIComponent(path)}?content=1`
  );
}

export async function getSessions(): Promise<JupyterSession[]> {
  return fetchJson<JupyterSession[]>("/api/jupyter/sessions");
}

export async function createSession(
  path: string,
  kernelName = "python3"
): Promise<JupyterSession> {
  const res = await fetch("/api/jupyter/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path,
      name: path.split("/").pop() || path,
      type: "notebook",
      kernel: { name: kernelName },
    }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function getKernels(): Promise<JupyterKernel[]> {
  return fetchJson<JupyterKernel[]>("/api/jupyter/kernels");
}

export async function restartKernel(kernelId: string): Promise<void> {
  const res = await fetch(`/api/jupyter/kernels/${kernelId}/restart`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

export async function interruptKernel(kernelId: string): Promise<void> {
  const res = await fetch(`/api/jupyter/kernels/${kernelId}/interrupt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

export async function shutdownKernel(kernelId: string): Promise<void> {
  const res = await fetch(`/api/jupyter/kernels/${kernelId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
}

export async function executeCell(
  kernelId: string,
  code: string
): Promise<{
  status: string;
  outputs: JupyterCellOutput[];
  execution_count?: number;
}> {
  const res = await fetch("/api/jupyter-exec", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kernelId, code }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

// --- Data lake (object store, read-only) ---

export interface LakeBucket {
  name: string;
  createdAt: string | null;
}

export interface LakeFolder {
  prefix: string;
  name: string;
}

export interface LakeObject {
  key: string;
  name: string;
  size: number;
  lastModified: string | null;
}

export interface LakeListing {
  bucket: string;
  prefix: string;
  folders: LakeFolder[];
  objects: LakeObject[];
  nextToken: string | null;
  truncated: boolean;
}

export interface LakeObjectDetail {
  bucket: string;
  key: string;
  size: number;
  contentType: string | null;
  lastModified: string | null;
  etag: string | null;
  preview: string | null;
  previewTruncated: boolean;
}

export async function getBuckets(): Promise<{ buckets: LakeBucket[]; defaultBucket: string }> {
  return fetchJson("/api/datalake/buckets");
}

export async function getLakeListing(
  bucket: string,
  prefix: string,
  token?: string
): Promise<LakeListing> {
  const q = new URLSearchParams({ bucket, prefix });
  if (token) q.set("token", token);
  return fetchJson(`/api/datalake/objects?${q}`);
}

export async function getLakeObject(bucket: string, key: string): Promise<LakeObjectDetail> {
  return fetchJson(`/api/datalake/object?${new URLSearchParams({ bucket, key })}`);
}

/** Parse s3://, s3a://, or s3n:// URIs into bucket + key/prefix. */
export function parseS3Uri(uri: string | undefined | null): { bucket: string; key: string } | null {
  if (!uri) return null;
  const m = /^s3[an]?:\/\/([^/]+)\/?(.*)$/.exec(uri);
  if (!m) return null;
  return { bucket: m[1], key: m[2] };
}

/** Data lake page link for a storage location (opens the folder). */
export function dataLakeHref(uri: string | undefined | null): string | null {
  const parsed = parseS3Uri(uri);
  if (!parsed) return null;
  const prefix = parsed.key && !parsed.key.endsWith("/") ? `${parsed.key}/` : parsed.key;
  return `/datalake?${new URLSearchParams({ bucket: parsed.bucket, prefix })}`;
}

// --- Jobs (Airflow 3.x API v2, read-only) ---

export interface AirflowDag {
  dag_id: string;
  dag_display_name?: string;
  description?: string | null;
  is_paused: boolean;
  is_stale?: boolean;
  fileloc?: string;
  owners?: string[];
  tags?: { name: string }[];
  timetable_summary?: string | null;
  timetable_description?: string | null;
  next_dagrun_logical_date?: string | null;
  next_dagrun_run_after?: string | null;
  last_parsed_time?: string | null;
  max_active_runs?: number;
  has_import_errors?: boolean;
}

export interface AirflowDagRun {
  dag_run_id: string;
  dag_id: string;
  state: string;
  run_type?: string;
  logical_date?: string | null;
  run_after?: string | null;
  queued_at?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  triggered_by?: string | null;
}

export interface AirflowTask {
  task_id: string;
  task_display_name?: string;
  operator_name?: string;
  downstream_task_ids?: string[];
  retries?: number;
}

export interface AirflowImportError {
  import_error_id: number;
  filename: string;
  stack_trace: string;
  timestamp?: string;
}

export async function getDags(): Promise<{ dags: AirflowDag[]; total_entries: number }> {
  return fetchJson("/api/airflow/dags?limit=200&order_by=dag_id");
}

export async function getRecentRuns(limit = 200): Promise<AirflowDagRun[]> {
  const data = await fetchJson<{ dag_runs: AirflowDagRun[] }>(
    `/api/airflow/dags/~/dagRuns?limit=${limit}&order_by=-run_after`
  );
  return data.dag_runs ?? [];
}

export async function getDagRuns(dagId: string, limit = 25): Promise<AirflowDagRun[]> {
  const data = await fetchJson<{ dag_runs: AirflowDagRun[] }>(
    `/api/airflow/dags/${encodeURIComponent(dagId)}/dagRuns?limit=${limit}&order_by=-run_after`
  );
  return data.dag_runs ?? [];
}

export async function getDagTasks(dagId: string): Promise<AirflowTask[]> {
  const data = await fetchJson<{ tasks: AirflowTask[] }>(
    `/api/airflow/dags/${encodeURIComponent(dagId)}/tasks`
  );
  return data.tasks ?? [];
}

export async function getImportErrors(): Promise<AirflowImportError[]> {
  const data = await fetchJson<{ import_errors: AirflowImportError[] }>("/api/airflow/importErrors");
  return data.import_errors ?? [];
}

// --- Auth ---

export async function getSessionUser(): Promise<string | null> {
  try {
    const res = await fetch("/api/auth/session");
    const data = await res.json();
    return data.user ?? null;
  } catch {
    return null;
  }
}

export async function logout(): Promise<void> {
  await fetch("/api/auth/logout", { method: "POST" });
}
