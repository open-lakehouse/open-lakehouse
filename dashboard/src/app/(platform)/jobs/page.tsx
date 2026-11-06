// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  ExternalLink,
  GitBranch,
  Loader2,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Search,
  Tag,
} from "lucide-react";
import {
  getDagRuns,
  getDags,
  getDagTasks,
  getImportErrors,
  getRecentRuns,
  type AirflowDag,
  type AirflowDagRun,
  type AirflowImportError,
  type AirflowTask,
} from "@/lib/api";
import { ErrorCard } from "@/components/error-card";
import { durationBetween, formatDateTime, relativeTime } from "@/lib/format";

/** Read-only view of Airflow DAGs ("jobs"). Selection lives in the URL (?dag=). */

const AIRFLOW_UI = "http://localhost:8085";

const stateStyle: Record<string, string> = {
  success: "bg-emerald-400/10 text-emerald-300",
  failed: "bg-red-400/10 text-red-300",
  running: "bg-sky-400/10 text-sky-300",
  queued: "bg-amber-400/10 text-amber-300",
  scheduled: "bg-amber-400/10 text-amber-300",
};

const dotStyle: Record<string, string> = {
  success: "bg-emerald-400",
  failed: "bg-red-400",
  running: "bg-sky-400 animate-pulse",
  queued: "bg-amber-400",
  scheduled: "bg-amber-400",
};

function StateBadge({ state }: { state: string | null | undefined }) {
  const s = (state ?? "none").toLowerCase();
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${
        stateStyle[s] ?? "bg-white/5 text-slate-400"
      }`}
    >
      {state ?? "no runs"}
    </span>
  );
}

/** Tiny run-history strip: one dot per recent run, oldest on the left. */
function RunStrip({ runs }: { runs: AirflowDagRun[] }) {
  if (runs.length === 0) return <span className="text-xs text-slate-600">—</span>;
  return (
    <span className="flex items-center gap-1">
      {[...runs].reverse().map((r) => (
        <span
          key={r.dag_run_id}
          title={`${r.state} · ${formatDateTime(r.run_after ?? r.logical_date ?? r.start_date)}`}
          className={`h-2.5 w-2.5 rounded-full ${dotStyle[r.state] ?? "bg-slate-600"}`}
        />
      ))}
    </span>
  );
}

function schedule(d: AirflowDag): string {
  return d.timetable_description || d.timetable_summary || "Manual only";
}

function nextRun(d: AirflowDag): string | null | undefined {
  return d.next_dagrun_run_after ?? d.next_dagrun_logical_date;
}

function JobDetail({ dag, onBack }: { dag: AirflowDag; onBack: () => void }) {
  const [runs, setRuns] = useState<AirflowDagRun[] | null>(null);
  const [tasks, setTasks] = useState<AirflowTask[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRuns(null);
    setTasks(null);
    setError(null);
    Promise.all([getDagRuns(dag.dag_id), getDagTasks(dag.dag_id)])
      .then(([r, t]) => {
        if (cancelled) return;
        setRuns(r);
        setTasks(t);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Failed to load"));
    return () => {
      cancelled = true;
    };
  }, [dag.dag_id]);

  return (
    <div className="space-y-6">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-white">
        <ArrowLeft size={14} /> All jobs
      </button>

      <div className="card space-y-4">
        <div className="flex flex-wrap items-start gap-3">
          <span className="icon-badge">
            <CalendarClock size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-xl font-semibold text-white">{dag.dag_display_name || dag.dag_id}</h2>
            {dag.dag_display_name && dag.dag_display_name !== dag.dag_id && (
              <p className="font-mono text-xs text-slate-500">{dag.dag_id}</p>
            )}
          </div>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
              dag.is_paused ? "bg-white/5 text-slate-400" : "bg-emerald-400/10 text-emerald-300"
            }`}
          >
            {dag.is_paused ? <PauseCircle size={12} /> : <PlayCircle size={12} />}
            {dag.is_paused ? "Paused" : "Active"}
          </span>
          <a
            href={`${AIRFLOW_UI}/dags/${encodeURIComponent(dag.dag_id)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/5 hover:text-white"
          >
            Open in Airflow <ExternalLink size={12} />
          </a>
        </div>
        {dag.description && <p className="text-sm text-slate-300">{dag.description}</p>}
        <div className="grid gap-4 sm:grid-cols-4">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-500">Schedule</p>
            <p className="text-sm text-slate-200">{schedule(dag)}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-500">Next run</p>
            <p className="text-sm text-slate-200">{dag.is_paused ? "—" : formatDateTime(nextRun(dag))}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-500">Owners</p>
            <p className="text-sm text-slate-200">{dag.owners?.join(", ") || "—"}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wider text-slate-500">Last parsed</p>
            <p className="text-sm text-slate-200">{relativeTime(dag.last_parsed_time)}</p>
          </div>
        </div>
        {dag.tags && dag.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {dag.tags.map((t) => (
              <span key={t.name} className="inline-flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-slate-300">
                <Tag size={10} /> {t.name}
              </span>
            ))}
          </div>
        )}
        {dag.fileloc && <p className="truncate font-mono text-[11px] text-slate-500">{dag.fileloc}</p>}
      </div>

      {error && <ErrorCard message={error} />}

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="card overflow-hidden p-0">
          <div className="border-b border-white/[0.06] px-6 py-4">
            <h3 className="text-sm font-semibold text-white">Recent runs</h3>
          </div>
          {runs === null && !error ? (
            <div className="flex justify-center py-12">
              <Loader2 size={20} className="animate-spin text-slate-500" />
            </div>
          ) : runs && runs.length === 0 ? (
            <p className="px-6 py-6 text-sm text-slate-500">This job has not run yet.</p>
          ) : (
            runs && (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="table-header">State</th>
                      <th className="table-header">Run</th>
                      <th className="table-header">Type</th>
                      <th className="table-header">Started</th>
                      <th className="table-header">Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.dag_run_id} className="border-t border-white/[0.04]">
                        <td className="table-cell">
                          <StateBadge state={r.state} />
                        </td>
                        <td className="table-cell max-w-[16rem] truncate font-mono text-xs" title={r.dag_run_id}>
                          {r.dag_run_id}
                        </td>
                        <td className="table-cell text-xs capitalize text-slate-400">
                          {(r.run_type ?? "").replace(/_/g, " ") || "—"}
                        </td>
                        <td className="table-cell text-slate-400" title={formatDateTime(r.start_date)}>
                          {relativeTime(r.start_date ?? r.queued_at)}
                        </td>
                        <td className="table-cell font-mono text-xs text-slate-400">
                          {durationBetween(r.start_date, r.end_date)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </div>

        <div className="card overflow-hidden p-0">
          <div className="border-b border-white/[0.06] px-5 py-4">
            <h3 className="text-sm font-semibold text-white">
              Tasks{tasks ? ` (${tasks.length})` : ""}
            </h3>
          </div>
          {tasks === null && !error ? (
            <div className="flex justify-center py-12">
              <Loader2 size={20} className="animate-spin text-slate-500" />
            </div>
          ) : (
            <ul className="divide-y divide-white/[0.04]">
              {(tasks ?? []).map((t) => (
                <li key={t.task_id} className="px-5 py-3">
                  <p className="flex items-center gap-2 text-sm text-white">
                    <GitBranch size={14} className="shrink-0 text-slate-500" />
                    <span className="truncate">{t.task_display_name || t.task_id}</span>
                  </p>
                  <p className="mt-0.5 pl-6 text-[11px] text-slate-500">
                    {t.operator_name || "Task"}
                    {t.downstream_task_ids && t.downstream_task_ids.length > 0
                      ? ` → ${t.downstream_task_ids.join(", ")}`
                      : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function JobsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selected = params.get("dag");

  const [dags, setDags] = useState<AirflowDag[] | null>(null);
  const [runs, setRuns] = useState<AirflowDagRun[]>([]);
  const [importErrors, setImportErrors] = useState<AirflowImportError[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState<"all" | "active" | "paused" | "failed">("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, r, ie] = await Promise.all([
        getDags(),
        getRecentRuns().catch(() => [] as AirflowDagRun[]),
        getImportErrors().catch(() => [] as AirflowImportError[]),
      ]);
      setDags(d.dags ?? []);
      setRuns(r);
      setImportErrors(ie);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runsByDag = useMemo(() => {
    const m = new Map<string, AirflowDagRun[]>();
    for (const r of runs) {
      const list = m.get(r.dag_id) ?? [];
      if (list.length < 10) list.push(r);
      m.set(r.dag_id, list);
    }
    return m;
  }, [runs]);

  const select = (dagId: string | null) =>
    router.push(dagId ? `${pathname}?dag=${encodeURIComponent(dagId)}` : pathname, { scroll: false });

  const q = filter.trim().toLowerCase();
  const visible = (dags ?? []).filter((d) => {
    const last = runsByDag.get(d.dag_id)?.[0];
    if (status === "active" && d.is_paused) return false;
    if (status === "paused" && !d.is_paused) return false;
    if (status === "failed" && last?.state !== "failed") return false;
    if (!q) return true;
    return (
      d.dag_id.toLowerCase().includes(q) ||
      (d.dag_display_name ?? "").toLowerCase().includes(q) ||
      (d.tags ?? []).some((t) => t.name.toLowerCase().includes(q)) ||
      (d.owners ?? []).some((o) => o.toLowerCase().includes(q))
    );
  });

  const counts = {
    all: dags?.length ?? 0,
    active: dags?.filter((d) => !d.is_paused).length ?? 0,
    paused: dags?.filter((d) => d.is_paused).length ?? 0,
    failed: dags?.filter((d) => runsByDag.get(d.dag_id)?.[0]?.state === "failed").length ?? 0,
  };

  const selectedDag = selected ? dags?.find((d) => d.dag_id === selected) : undefined;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Jobs</p>
          <h1 className="text-2xl font-bold text-white">Jobs</h1>
          <p className="mt-1 text-sm text-slate-400">
            Airflow DAGs, their schedules and recent runs. Read-only — trigger and pause from Airflow.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href={AIRFLOW_UI}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5 hover:text-white"
          >
            Airflow UI <ExternalLink size={12} />
          </a>
          <button
            onClick={load}
            className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5 hover:text-white"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <ErrorCard
          title="Airflow unavailable"
          message={error}
          onRetry={load}
          hint="Start it with ./lakehouse start airflow. If Airflow is up, check AIRFLOW_USERNAME / AIRFLOW_PASSWORD for the dashboard."
        />
      )}

      {importErrors.length > 0 && !selected && (
        <details className="card border-amber-500/30 bg-amber-500/5">
          <summary className="flex cursor-pointer items-center gap-2 text-sm text-amber-200">
            <AlertTriangle size={16} />
            {importErrors.length} DAG file{importErrors.length === 1 ? "" : "s"} failed to import
          </summary>
          <ul className="mt-3 space-y-3">
            {importErrors.map((e) => (
              <li key={e.import_error_id}>
                <p className="font-mono text-xs text-slate-300">{e.filename}</p>
                <pre className="mt-1 max-h-40 overflow-auto rounded bg-surface-dark p-2 font-mono text-[11px] text-red-300">
                  {e.stack_trace}
                </pre>
              </li>
            ))}
          </ul>
        </details>
      )}

      {loading && !dags ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={22} className="animate-spin text-slate-500" />
        </div>
      ) : selected && dags ? (
        selectedDag ? (
          <JobDetail dag={selectedDag} onBack={() => select(null)} />
        ) : (
          <ErrorCard message={`Job '${selected}' was not found.`} onRetry={() => select(null)} />
        )
      ) : (
        dags && (
          <div className="card overflow-hidden p-0">
            <div className="flex flex-wrap items-center gap-3 border-b border-white/[0.06] px-4 py-3">
              <div className="flex gap-1 rounded-lg bg-surface-dark p-1">
                {(["all", "active", "paused", "failed"] as const).map((k) => (
                  <button
                    key={k}
                    onClick={() => setStatus(k)}
                    className={`rounded-md px-3 py-1 text-xs capitalize ${
                      status === k ? "bg-surface-light text-white" : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {k} <span className="text-slate-500">{counts[k]}</span>
                  </button>
                ))}
              </div>
              <div className="relative min-w-[12rem] flex-1">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Search by name, tag or owner..."
                  className="w-full rounded-md border border-slate-700 bg-surface-dark py-1.5 pl-8 pr-2 text-xs text-white placeholder-slate-500 outline-none focus:border-accent/50"
                />
              </div>
            </div>

            {dags.length === 0 ? (
              <div className="px-6 py-14 text-center">
                <CalendarClock size={28} className="mx-auto text-slate-600" />
                <p className="mt-3 text-sm text-slate-300">No jobs yet</p>
                <p className="mt-1 text-xs text-slate-500">
                  Drop a DAG file into <code className="font-mono text-slate-400">dags/</code> — Airflow picks it up
                  automatically.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="table-header">Job</th>
                      <th className="table-header">Schedule</th>
                      <th className="table-header">Last run</th>
                      <th className="table-header">Recent</th>
                      <th className="table-header">Next run</th>
                      <th className="table-header">Owner</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((d) => {
                      const dr = runsByDag.get(d.dag_id) ?? [];
                      const last = dr[0];
                      return (
                        <tr
                          key={d.dag_id}
                          onClick={() => select(d.dag_id)}
                          className="cursor-pointer border-t border-white/[0.04] hover:bg-white/[0.03]"
                        >
                          <td className="table-cell">
                            <div className="flex items-center gap-2">
                              {d.is_paused ? (
                                <PauseCircle size={16} className="shrink-0 text-slate-500" aria-label="Paused" />
                              ) : (
                                <PlayCircle size={16} className="shrink-0 text-emerald-400" aria-label="Active" />
                              )}
                              <div className="min-w-0">
                                <p className="truncate font-medium text-white">{d.dag_display_name || d.dag_id}</p>
                                {d.tags && d.tags.length > 0 && (
                                  <p className="truncate text-[11px] text-slate-500">
                                    {d.tags.map((t) => t.name).join(" · ")}
                                  </p>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="table-cell text-slate-400">{schedule(d)}</td>
                          <td className="table-cell">
                            <div className="flex items-center gap-2">
                              <StateBadge state={last?.state} />
                              {last && (
                                <span className="text-xs text-slate-500">
                                  {relativeTime(last.start_date ?? last.run_after)}
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="table-cell">
                            <RunStrip runs={dr} />
                          </td>
                          <td className="table-cell text-slate-400">
                            {d.is_paused ? "—" : relativeTime(nextRun(d))}
                          </td>
                          <td className="table-cell text-slate-400">{d.owners?.join(", ") || "—"}</td>
                        </tr>
                      );
                    })}
                    {visible.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-4 py-12 text-center text-sm text-slate-500">
                          No jobs match.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      )}
    </div>
  );
}

export default function JobsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-20">
          <Loader2 size={22} className="animate-spin text-slate-500" />
        </div>
      }
    >
      <JobsView />
    </Suspense>
  );
}
