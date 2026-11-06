// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { useEffect, useState, useCallback } from "react";
import {
  FlaskConical,
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronRight,
  ArrowLeft,
  Loader2,
  Search,
  ExternalLink,
} from "lucide-react";
import { getExperiments, getExperimentRuns } from "@/lib/api";
import type { MlflowExperiment, MlflowRun } from "@/lib/api";
import { ErrorCard } from "@/components/error-card";

function formatTime(ms: number): string {
  return new Date(ms).toLocaleString();
}

function formatDuration(start: number, end?: number): string {
  const diff = (end ?? Date.now()) - start;
  if (diff < 1000) return `${diff}ms`;
  if (diff < 60000) return `${(diff / 1000).toFixed(1)}s`;
  return `${(diff / 60000).toFixed(1)}m`;
}

const statusIcon = {
  RUNNING: <Play size={14} className="text-blue-400" />,
  FINISHED: <CheckCircle2 size={14} className="text-emerald-400" />,
  FAILED: <XCircle size={14} className="text-red-400" />,
  KILLED: <XCircle size={14} className="text-amber-400" />,
};

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<MlflowExperiment[]>([]);
  const [selectedExp, setSelectedExp] = useState<MlflowExperiment | null>(null);
  const [runs, setRuns] = useState<MlflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const fetchExperiments = useCallback(() => {
    setLoading(true);
    setError(null);
    getExperiments()
      .then(setExperiments)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchExperiments();
  }, [fetchExperiments]);

  async function selectExperiment(exp: MlflowExperiment) {
    setSelectedExp(exp);
    setLoading(true);
    setError(null);
    try {
      setRuns(await getExperimentRuns(exp.experiment_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Experiments</h1>
          <p className="mt-1 text-sm text-slate-400">
            MLflow experiment tracking & runs
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="http://localhost:5000"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary flex items-center gap-2"
          >
            Open MLflow
            <ExternalLink size={14} />
          </a>
        </div>
      </div>

      {error && (
        <ErrorCard
          message={error}
          onRetry={selectedExp ? () => selectExperiment(selectedExp) : fetchExperiments}
          hint="Check if MLflow is running with: ./lakehouse status"
        />
      )}

      {loading && !selectedExp ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-slate-500" />
        </div>
      ) : !selectedExp ? (
        <div className="space-y-4">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter by name..."
              className="w-full rounded-lg border border-slate-700 bg-surface-dark py-2 pl-9 pr-3 text-sm text-white placeholder-slate-500 outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/25"
            />
          </div>
          <div className="space-y-2">
          {experiments.filter((exp) => exp.name.toLowerCase().includes(searchQuery.toLowerCase())).map((exp) => (
            <button
              key={exp.experiment_id}
              onClick={() => selectExperiment(exp)}
              className="card group flex w-full items-center gap-4 text-left transition-colors hover:border-accent/30"
            >
              <FlaskConical size={18} className="text-accent" />
              <div className="flex-1">
                <p className="text-sm font-medium text-white group-hover:text-accent">
                  {exp.name}
                </p>
                <p className="text-xs text-slate-500">
                  ID: {exp.experiment_id}
                  {exp.lifecycle_stage !== "active" &&
                    ` \u00b7 ${exp.lifecycle_stage}`}
                </p>
              </div>
              <ChevronRight
                size={16}
                className="text-slate-600 group-hover:text-slate-400"
              />
            </button>
          ))}
          {experiments.filter((exp) => exp.name.toLowerCase().includes(searchQuery.toLowerCase())).length === 0 && (
            <p className="text-sm text-slate-500">No experiments found</p>
          )}
          </div>
        </div>
      ) : (
        /* Runs view */
        <div className="space-y-4">
          <button
            onClick={() => {
              setSelectedExp(null);
              setRuns([]);
            }}
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white"
          >
            <ArrowLeft size={16} />
            Back to experiments
          </button>

          <div className="card">
            <h2 className="text-lg font-semibold text-white">
              {selectedExp.name}
            </h2>
            <p className="mt-1 font-mono text-xs text-slate-500">
              {selectedExp.artifact_location}
            </p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-10">
              <Loader2 size={24} className="animate-spin text-slate-500" />
            </div>
          ) : (
            <div className="card overflow-hidden p-0">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-800/50">
                    <th className="table-header">Status</th>
                    <th className="table-header">Run Name</th>
                    <th className="table-header">Start Time</th>
                    <th className="table-header">Duration</th>
                    <th className="table-header">Metrics</th>
                    <th className="table-header">Params</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr
                      key={run.info.run_id}
                      className="border-b border-slate-800/30 hover:bg-slate-800/30"
                    >
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          {statusIcon[
                            run.info.status as keyof typeof statusIcon
                          ] ?? (
                            <Clock size={14} className="text-slate-500" />
                          )}
                          <span className="text-xs">{run.info.status}</span>
                        </div>
                      </td>
                      <td className="table-cell font-medium text-white">
                        {run.info.run_name ?? run.info.run_id.slice(0, 8)}
                      </td>
                      <td className="table-cell text-xs">
                        {formatTime(run.info.start_time)}
                      </td>
                      <td className="table-cell font-mono text-xs">
                        {formatDuration(
                          run.info.start_time,
                          run.info.end_time
                        )}
                      </td>
                      <td className="table-cell">
                        <div className="flex flex-wrap gap-1">
                          {(run.data.metrics ?? []).slice(0, 3).map((m) => (
                            <span
                              key={m.key}
                              className="rounded bg-emerald-900/30 px-1.5 py-0.5 text-[10px] text-emerald-300"
                            >
                              {m.key}: {m.value.toFixed(4)}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="table-cell">
                        <div className="flex flex-wrap gap-1">
                          {(run.data.params ?? []).slice(0, 3).map((p) => (
                            <span
                              key={p.key}
                              className="rounded bg-blue-900/30 px-1.5 py-0.5 text-[10px] text-blue-300"
                            >
                              {p.key}={p.value}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {runs.length === 0 && (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-4 py-8 text-center text-sm text-slate-500"
                      >
                        No runs in this experiment
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
