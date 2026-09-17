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
  created_at?: number;
  properties?: Record<string, string>;
}

export interface Schema {
  name: string;
  catalog_name: string;
  comment?: string;
  created_at?: number;
}

export interface Table {
  name: string;
  catalog_name: string;
  schema_name: string;
  table_type: string;
  data_source_format?: string;
  storage_location?: string;
  columns?: Column[];
  created_at?: number;
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

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
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
