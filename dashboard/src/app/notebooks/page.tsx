// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import CodeExecGuard from "@/components/code-exec-guard";
import {
  BookOpen,
  FileText,
  Folder,
  ArrowLeft,
  Loader2,
  AlertCircle,
  ExternalLink,
  Play,
  ChevronDown,
  ChevronRight,
  Code2,
  Type,
  Hash,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Terminal,
  Square,
  SkipForward,
  RotateCw,
  CircleStop,
  Power,
} from "lucide-react";
import {
  getNotebooks,
  getNotebookContent,
  getSessions,
  createSession,
  executeCell,
  restartKernel,
  interruptKernel,
  shutdownKernel,
} from "@/lib/api";
import { sanitizeHtml } from "@/lib/sanitize";
import type {
  JupyterContentItem,
  JupyterCell,
  JupyterCellOutput,
  JupyterSession,
} from "@/lib/api";

type CellExecState = "idle" | "running" | "success" | "error";

function toStr(v: unknown, sep = ""): string {
  if (Array.isArray(v)) return v.join(sep);
  if (typeof v === "string") return v;
  return String(v ?? "");
}

function cellSource(cell: JupyterCell): string {
  return toStr(cell.source);
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

function formatSize(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderMarkdown(source: string): string {
  let html = source;
  html = html.replace(
    /```(\w*)\n([\s\S]*?)```/g,
    '<pre class="rounded-lg bg-slate-900 border border-slate-700 p-3 my-2 overflow-x-auto"><code class="text-xs font-mono text-slate-300">$2</code></pre>'
  );
  html = html.replace(
    /^### (.+)$/gm,
    '<h3 class="text-base font-semibold text-white mt-4 mb-2">$1</h3>'
  );
  html = html.replace(
    /^## (.+)$/gm,
    '<h2 class="text-lg font-semibold text-white mt-5 mb-2">$1</h2>'
  );
  html = html.replace(
    /^# (.+)$/gm,
    '<h1 class="text-xl font-bold text-white mt-6 mb-3">$1</h1>'
  );
  html = html.replace(
    /\*\*(.+?)\*\*/g,
    '<strong class="text-white font-semibold">$1</strong>'
  );
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(
    /`([^`]+)`/g,
    '<code class="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-amber-300 font-mono">$1</code>'
  );
  html = html.replace(
    /^- (.+)$/gm,
    '<li class="ml-4 list-disc text-slate-300">$1</li>'
  );
  html = html.replace(
    /^(\d+)\. (.+)$/gm,
    '<li class="ml-4 list-decimal text-slate-300">$2</li>'
  );
  html = html.replace(/^---$/gm, '<hr class="border-slate-700 my-4" />');
  html = html.replace(
    /^(?!<[h|l|p|u|o|d|b|c|s|e|t|a|i|H])((?!^\s*$).+)$/gm,
    '<p class="text-slate-300 my-1">$1</p>'
  );
  return html;
}

function CellOutputDisplay({ output }: { output: JupyterCellOutput }) {
  if (output.output_type === "stream") {
    return (
      <pre className="whitespace-pre-wrap rounded bg-slate-900 p-3 font-mono text-xs text-slate-300">
        {toStr(output.text)}
      </pre>
    );
  }

  if (output.output_type === "error") {
    return (
      <div className="rounded border border-red-900/50 bg-red-950/30 p-3">
        <p className="font-mono text-xs font-semibold text-red-400">
          {output.ename}: {output.evalue}
        </p>
        {output.traceback && (
          <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px] text-red-300/80">
            {toStr(output.traceback, "\n").replace(/\x1b\[[0-9;]*m/g, "")}
          </pre>
        )}
      </div>
    );
  }

  if (
    output.output_type === "execute_result" ||
    output.output_type === "display_data"
  ) {
    const data = output.data ?? {};
    // Check images first — matplotlib outputs include both image/png and a
    // text/plain placeholder like "<Figure size 800x400 with 1 Axes>".
    // Rendering text/plain first would hide the actual image.
    if (data["image/png"]) {
      return (
        <div className="rounded bg-slate-900 p-3">
          <img
            src={`data:image/png;base64,${toStr(data["image/png"])}`}
            alt="Cell output"
            className="max-w-full"
            style={{ maxHeight: '600px', objectFit: 'contain' }}
          />
        </div>
      );
    }
    if (data["image/svg+xml"]) {
      return (
        <div
          className="max-w-full overflow-auto rounded bg-slate-900 p-3"
          style={{ maxHeight: '600px' }}
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(toStr(data["image/svg+xml"])) }}
        />
      );
    }
    if (data["text/html"]) {
      const htmlContent = toStr(data["text/html"]);
      return (
        <div
          className="notebook-html-output overflow-x-auto rounded bg-slate-900 p-3 text-xs text-slate-300"
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(htmlContent) }}
        />
      );
    }
    if (data["text/plain"]) {
      const text = toStr(data["text/plain"]);
      return (
        <pre className="whitespace-pre-wrap rounded bg-slate-900 p-3 font-mono text-xs text-slate-300">
          {text}
        </pre>
      );
    }
  }

  return null;
}

function NotebookCell({
  cell,
  index,
  collapsed,
  onToggle,
  execState,
  liveOutputs,
  executionCount,
  onRun,
  kernelReady,
}: {
  cell: JupyterCell;
  index: number;
  collapsed: boolean;
  onToggle: () => void;
  execState: CellExecState;
  liveOutputs: JupyterCellOutput[] | null;
  executionCount: number | null;
  onRun: () => void;
  kernelReady: boolean;
}) {
  const source = cellSource(cell);
  const outputs = liveOutputs ?? cell.outputs ?? [];
  const hasOutputs = outputs.length > 0;
  const displayCount = executionCount ?? cell.execution_count;

  if (cell.cell_type === "markdown") {
    return (
      <div className="group relative border-l-2 border-blue-500/30 pl-4 hover:border-blue-500/60">
        <div className="mb-1 flex items-center gap-2">
          <Type size={12} className="text-blue-400" />
          <span className="text-[10px] uppercase tracking-wider text-slate-600">
            Markdown
          </span>
        </div>
        <div
          className="prose-sm text-sm leading-relaxed"
          dangerouslySetInnerHTML={{ __html: sanitizeHtml(renderMarkdown(source)) }}
        />
      </div>
    );
  }

  const borderColor =
    execState === "running"
      ? "border-amber-500/60"
      : execState === "error"
      ? "border-red-500/60"
      : execState === "success"
      ? "border-emerald-500/60"
      : "border-emerald-500/30";

  return (
    <div
      className={`group relative border-l-2 pl-4 transition-colors hover:border-emerald-500/60 ${borderColor}`}
    >
      <div className="mb-1 flex w-full items-center gap-2">
        {kernelReady && (
          <button
            onClick={onRun}
            disabled={execState === "running"}
            className="flex items-center justify-center rounded p-0.5 text-slate-500 transition-colors hover:bg-slate-800 hover:text-emerald-400 disabled:opacity-50"
            title="Run cell"
            aria-label="Run cell"
          >
            {execState === "running" ? (
              <Loader2 size={14} className="animate-spin text-amber-400" />
            ) : (
              <Play size={14} />
            )}
          </button>
        )}
        <button
          onClick={onToggle}
          className="flex flex-1 items-center gap-2 text-left"
        >
          <Code2 size={12} className="text-emerald-400" />
          <span className="text-[10px] uppercase tracking-wider text-slate-600">
            Code
          </span>
          {displayCount != null && (
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                execState === "running"
                  ? "bg-amber-900/30 text-amber-400"
                  : "bg-slate-800 text-slate-400"
              }`}
            >
              [{execState === "running" ? "*" : displayCount}]
            </span>
          )}
          {execState === "success" && (
            <CheckCircle2 size={12} className="text-emerald-400" />
          )}
          {execState === "error" && (
            <XCircle size={12} className="text-red-400" />
          )}
          {hasOutputs && execState === "idle" && (
            <span className="rounded bg-emerald-900/30 px-1.5 py-0.5 text-[10px] text-emerald-400">
              {outputs.length} output{outputs.length !== 1 ? "s" : ""}
            </span>
          )}
          <span className="ml-auto text-slate-600">
            {collapsed ? (
              <ChevronRight size={14} />
            ) : (
              <ChevronDown size={14} />
            )}
          </span>
        </button>
      </div>

      {!collapsed && (
        <div className="space-y-2">
          <pre className="overflow-x-auto rounded-lg border border-slate-700 bg-slate-900 p-3">
            <code className="font-mono text-xs text-slate-300">{source}</code>
          </pre>

          {execState === "running" && outputs.length === 0 && (
            <div className="flex items-center gap-2 rounded border border-amber-900/30 bg-amber-950/20 px-3 py-2">
              <Loader2 size={14} className="animate-spin text-amber-400" />
              <span className="text-xs text-amber-300">Executing...</span>
            </div>
          )}

          {hasOutputs && (
            <div className="ml-2 space-y-2 border-l border-slate-700 pl-3">
              <span className="text-[10px] uppercase tracking-wider text-slate-600">
                Output
              </span>
              {outputs.map((output, i) => (
                <CellOutputDisplay key={i} output={output} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function NotebooksPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const notebookParam = searchParams.get("nb");

  const [items, setItems] = useState<JupyterContentItem[]>([]);
  const [currentPath, setCurrentPath] = useState("work");
  const [pathHistory, setPathHistory] = useState<string[]>([]);
  const [selectedNotebook, setSelectedNotebook] =
    useState<JupyterContentItem | null>(null);
  const [cells, setCells] = useState<JupyterCell[]>([]);
  const [collapsedCells, setCollapsedCells] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<JupyterSession[]>([]);
  const [startingSession, setStartingSession] = useState(false);
  const [filter, setFilter] = useState<"all" | "code" | "markdown">("all");

  // When the URL has no ?nb= param (e.g. sidebar click), close any open notebook
  useEffect(() => {
    if (!notebookParam && selectedNotebook) {
      setSelectedNotebook(null);
      setCells([]);
      setCellExecStates(new Map());
      setCellLiveOutputs(new Map());
      setCellExecCounts(new Map());
      setRunningAll(false);
      cancelRunAllRef.current = false;
    }
  }, [notebookParam]); // eslint-disable-line react-hooks/exhaustive-deps

  const [cellExecStates, setCellExecStates] = useState<
    Map<number, CellExecState>
  >(new Map());
  const [cellLiveOutputs, setCellLiveOutputs] = useState<
    Map<number, JupyterCellOutput[]>
  >(new Map());
  const [cellExecCounts, setCellExecCounts] = useState<
    Map<number, number>
  >(new Map());
  const [runningAll, setRunningAll] = useState(false);
  const cancelRunAllRef = useRef(false);
  const [restartingKernel, setRestartingKernel] = useState(false);
  const [interruptingKernel, setInterruptingKernel] = useState(false);

  const jupyterBaseUrl = "http://localhost:8889";

  const fetchItems = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getNotebooks(path);
      setItems(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load notebooks");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSessions = useCallback(async () => {
    try {
      const s = await getSessions();
      setSessions(s);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    fetchItems(currentPath);
    fetchSessions();
  }, [currentPath, fetchItems, fetchSessions]);

  async function openNotebook(item: JupyterContentItem) {
    setLoading(true);
    setError(null);
    try {
      const content = await getNotebookContent(item.path);
      if (
        content.content &&
        typeof content.content === "object" &&
        "cells" in content.content
      ) {
        const nb = content.content;
        setSelectedNotebook(content);
        setCells(nb.cells);
        setCollapsedCells(new Set());
        setCellExecStates(new Map());
        setCellLiveOutputs(new Map());
        setCellExecCounts(new Map());
        router.push(`/notebooks?nb=${encodeURIComponent(item.path)}`, { scroll: false });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load notebook");
    } finally {
      setLoading(false);
    }
  }

  function navigateToDir(item: JupyterContentItem) {
    setPathHistory((prev) => [...prev, currentPath]);
    setCurrentPath(item.path);
  }

  function goBack() {
    if (selectedNotebook) {
      setSelectedNotebook(null);
      setCells([]);
      setCellExecStates(new Map());
      setCellLiveOutputs(new Map());
      setCellExecCounts(new Map());
      setRunningAll(false);
      cancelRunAllRef.current = false;
      router.push("/notebooks", { scroll: false });
      return;
    }
    const prev = pathHistory[pathHistory.length - 1];
    if (prev !== undefined) {
      setPathHistory((h) => h.slice(0, -1));
      setCurrentPath(prev);
    }
  }

  function toggleCell(index: number) {
    setCollapsedCells((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  function collapseAllCode() {
    const codeIndices = cells
      .map((c, i) => (c.cell_type === "code" ? i : -1))
      .filter((i) => i >= 0);
    setCollapsedCells(new Set(codeIndices));
  }

  function expandAll() {
    setCollapsedCells(new Set());
  }

  async function startKernel(path: string) {
    setStartingSession(true);
    setError(null);
    try {
      await createSession(path);
      await fetchSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start kernel");
    } finally {
      setStartingSession(false);
    }
  }

  function getSessionForPath(path: string): JupyterSession | undefined {
    return sessions.find((s) => s.path === path);
  }

  function getActiveKernelId(): string | null {
    if (!selectedNotebook) return null;
    const session = getSessionForPath(selectedNotebook.path);
    return session?.kernel?.id ?? null;
  }

  async function runCell(index: number) {
    const kernelId = getActiveKernelId();
    if (!kernelId) {
      setError("No active kernel. Start a kernel first.");
      return;
    }
    const cell = cells[index];
    if (!cell || cell.cell_type !== "code") return;

    const code = cellSource(cell);
    if (!code.trim()) return;

    setCellExecStates((prev) => new Map(prev).set(index, "running"));
    setCellLiveOutputs((prev) => new Map(prev).set(index, []));
    setCollapsedCells((prev) => {
      const next = new Set(prev);
      next.delete(index);
      return next;
    });

    try {
      const result = await executeCell(kernelId, code);
      setCellLiveOutputs((prev) =>
        new Map(prev).set(index, result.outputs)
      );
      if (result.execution_count != null) {
        setCellExecCounts((prev) =>
          new Map(prev).set(index, result.execution_count!)
        );
      }
      setCellExecStates((prev) =>
        new Map(prev).set(
          index,
          result.status === "ok" ? "success" : "error"
        )
      );
      return result.status === "ok";
    } catch (e) {
      const message = e instanceof Error ? e.message : "Execution failed";
      setCellLiveOutputs((prev) =>
        new Map(prev).set(index, [
          {
            output_type: "error",
            ename: "ExecutionError",
            evalue: message,
            traceback: [],
          },
        ])
      );
      setCellExecStates((prev) => new Map(prev).set(index, "error"));
      return false;
    }
  }

  async function runAllCells() {
    const kernelId = getActiveKernelId();
    if (!kernelId) {
      setError("No active kernel. Start a kernel first.");
      return;
    }

    setRunningAll(true);
    cancelRunAllRef.current = false;

    const codeIndices = cells
      .map((c, i) => (c.cell_type === "code" ? i : -1))
      .filter((i) => i >= 0);

    for (const idx of codeIndices) {
      if (cancelRunAllRef.current) break;
      const ok = await runCell(idx);
      if (!ok) break;
    }

    setRunningAll(false);
  }

  function stopRunAll() {
    cancelRunAllRef.current = true;
  }

  async function handleInterruptKernel() {
    const kid = getActiveKernelId();
    if (!kid) return;
    setInterruptingKernel(true);
    cancelRunAllRef.current = true;
    try {
      await interruptKernel(kid);
      setCellExecStates((prev) => {
        const next = new Map(prev);
        for (const [idx, state] of next) {
          if (state === "running") next.set(idx, "idle");
        }
        return next;
      });
      setRunningAll(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to interrupt kernel");
    } finally {
      setInterruptingKernel(false);
    }
  }

  async function handleRestartKernel() {
    const kid = getActiveKernelId();
    if (!kid) return;
    setRestartingKernel(true);
    cancelRunAllRef.current = true;
    try {
      await restartKernel(kid);
      setCellExecStates(new Map());
      setCellLiveOutputs(new Map());
      setCellExecCounts(new Map());
      setRunningAll(false);
      await fetchSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to restart kernel");
    } finally {
      setRestartingKernel(false);
    }
  }

  async function handleShutdownKernel() {
    const kid = getActiveKernelId();
    if (!kid) return;
    cancelRunAllRef.current = true;
    try {
      await shutdownKernel(kid);
      setCellExecStates(new Map());
      setRunningAll(false);
      await fetchSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to shutdown kernel");
    }
  }

  const filteredCells = cells.filter((c) => {
    if (filter === "all") return true;
    return c.cell_type === filter;
  });

  const cellStats = {
    total: cells.length,
    code: cells.filter((c) => c.cell_type === "code").length,
    markdown: cells.filter((c) => c.cell_type === "markdown").length,
    executed: cells.filter((c) => c.execution_count != null).length,
  };

  const kernelId = getActiveKernelId();
  const kernelReady = !!kernelId;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Notebooks</h1>
          <p className="mt-1 text-sm text-slate-400">
            Browse, view, and execute Jupyter notebooks
          </p>
        </div>
        <a
          href={jupyterBaseUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-accent hover:text-white"
        >
          <Terminal size={16} />
          Open JupyterLab
          <ExternalLink size={14} />
        </a>
      </div>

      {error && (
        <div className="card flex items-center gap-3 border-red-900/50 bg-red-950/30 text-red-300">
          <AlertCircle size={18} />
          <span className="text-sm">{error}</span>
          <button
            onClick={() => setError(null)}
            className="ml-auto text-red-400 hover:text-red-300"
            aria-label="Close error"
          >
            <XCircle size={16} />
          </button>
        </div>
      )}

      {selectedNotebook ? (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <button
              onClick={goBack}
              className="flex items-center gap-2 text-sm text-slate-400 hover:text-white"
            >
              <ArrowLeft size={16} />
              Back
            </button>
          </div>

          {/* Notebook header */}
          <div className="card">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
                  <BookOpen size={20} className="text-accent" />
                  {selectedNotebook.name}
                </h2>
                <p className="mt-1 font-mono text-xs text-slate-500">
                  {selectedNotebook.path}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Modified: {formatDate(selectedNotebook.last_modified)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {(() => {
                  const session = getSessionForPath(selectedNotebook.path);
                  return session ? (
                    <>
                      <span className="flex items-center gap-1.5 rounded-full bg-emerald-900/30 px-3 py-1 text-xs text-emerald-400">
                        <CheckCircle2 size={12} />
                        Kernel: {session.kernel.execution_state}
                      </span>
                      <button
                        onClick={handleInterruptKernel}
                        disabled={interruptingKernel}
                        className="flex items-center gap-1.5 rounded-lg border border-amber-700/50 px-2.5 py-1 text-xs text-amber-400 hover:bg-amber-950/30"
                        title="Interrupt execution"
                      >
                        {interruptingKernel ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <CircleStop size={12} />
                        )}
                        Interrupt
                      </button>
                      <button
                        onClick={handleRestartKernel}
                        disabled={restartingKernel}
                        className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                        title="Restart kernel (clears all state)"
                      >
                        {restartingKernel ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <RotateCw size={12} />
                        )}
                        Restart
                      </button>
                      <button
                        onClick={handleShutdownKernel}
                        className="flex items-center gap-1.5 rounded-lg border border-red-800/50 px-2.5 py-1 text-xs text-red-400 hover:bg-red-950/30"
                        title="Shutdown kernel"
                        aria-label="Shutdown kernel"
                      >
                        <Power size={12} />
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => startKernel(selectedNotebook.path)}
                      disabled={startingSession}
                      className="btn-primary flex items-center gap-2 text-xs"
                    >
                      {startingSession ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Play size={14} />
                      )}
                      Start Kernel
                    </button>
                  );
                })()}
                <a
                  href={`${jupyterBaseUrl}/lab/tree/${selectedNotebook.path}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:border-accent hover:text-white"
                >
                  Open in Jupyter
                  <ExternalLink size={12} />
                </a>
              </div>
            </div>

            {/* Stats bar + actions */}
            <div className="mt-4 flex items-center gap-4 border-t border-slate-800 pt-4">
              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <Hash size={12} />
                {cellStats.total} cells
              </span>
              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <Code2 size={12} />
                {cellStats.code} code
              </span>
              <span className="flex items-center gap-1.5 text-xs text-slate-400">
                <Type size={12} />
                {cellStats.markdown} markdown
              </span>
              {cellStats.executed > 0 && (
                <span className="flex items-center gap-1.5 text-xs text-emerald-400">
                  <CheckCircle2 size={12} />
                  {cellStats.executed} executed
                </span>
              )}

              <div className="ml-auto flex items-center gap-2">
                {kernelReady && (
                  <>
                    {runningAll ? (
                      <button
                        onClick={handleInterruptKernel}
                        className="flex items-center gap-1.5 rounded-lg border border-red-700 bg-red-950/30 px-3 py-1 text-xs text-red-400 hover:bg-red-950/50"
                      >
                        <Square size={12} />
                        Stop Execution
                      </button>
                    ) : (
                      <button
                        onClick={runAllCells}
                        className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700"
                      >
                        <SkipForward size={12} />
                        Run All
                      </button>
                    )}
                  </>
                )}
                <div className="flex rounded-lg border border-slate-700">
                  {(["all", "code", "markdown"] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFilter(f)}
                      className={`px-3 py-1 text-xs capitalize transition-colors ${
                        filter === f
                          ? "bg-accent/20 text-accent"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
                <button
                  onClick={collapseAllCode}
                  className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-white"
                >
                  Collapse code
                </button>
                <button
                  onClick={expandAll}
                  className="rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-white"
                >
                  Expand all
                </button>
              </div>
            </div>

            {!kernelReady && (
              <div className="mt-3 flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2">
                <AlertCircle size={14} className="text-amber-400" />
                <span className="text-xs text-slate-400">
                  Start a kernel to execute cells. You can also{" "}
                  <a
                    href={`${jupyterBaseUrl}/lab/tree/${selectedNotebook.path}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent hover:underline"
                  >
                    open in JupyterLab
                  </a>{" "}
                  for the full notebook experience.
                </span>
              </div>
            )}
          </div>

          {/* Cells */}
          <div className="space-y-4">
            {filteredCells.map((cell) => {
              const realIndex = cells.indexOf(cell);
              return (
                <NotebookCell
                  key={realIndex}
                  cell={cell}
                  index={realIndex}
                  collapsed={collapsedCells.has(realIndex)}
                  onToggle={() => toggleCell(realIndex)}
                  execState={cellExecStates.get(realIndex) ?? "idle"}
                  liveOutputs={cellLiveOutputs.get(realIndex) ?? null}
                  executionCount={cellExecCounts.get(realIndex) ?? null}
                  onRun={() => runCell(realIndex)}
                  kernelReady={kernelReady}
                />
              );
            })}
          </div>
        </div>
      ) : loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-slate-500" />
        </div>
      ) : (
        /* File browser */
        <div className="space-y-4">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2">
            {currentPath !== "work" && (
              <button
                onClick={goBack}
                className="flex items-center gap-2 text-sm text-slate-400 hover:text-white"
              >
                <ArrowLeft size={16} />
                Back
              </button>
            )}
            <div className="flex items-center gap-1 font-mono text-xs text-slate-500">
              {currentPath.split("/").map((part, i, arr) => (
                <span key={i} className="flex items-center gap-1">
                  {i > 0 && <span className="text-slate-600">/</span>}
                  <span
                    className={
                      i === arr.length - 1
                        ? "text-slate-300"
                        : "text-slate-500"
                    }
                  >
                    {part}
                  </span>
                </span>
              ))}
            </div>
            <button
              onClick={() => fetchItems(currentPath)}
              className="ml-auto rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-white"
              title="Refresh"
              aria-label="Refresh"
            >
              <RefreshCw size={14} />
            </button>
          </div>

          {/* Active sessions */}
          {sessions.length > 0 && (
            <div className="card border-emerald-900/30 bg-emerald-950/10">
              <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-emerald-400">
                <Play size={14} />
                Active Kernels ({sessions.length})
              </h3>
              <div className="space-y-2">
                {sessions.map((session) => (
                  <div
                    key={session.id}
                    className="flex items-center justify-between rounded-lg border border-emerald-900/20 bg-surface/50 px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <FileText size={14} className="text-amber-400" />
                      <span className="text-sm text-white">
                        {session.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] ${
                          session.kernel.execution_state === "idle"
                            ? "bg-emerald-900/30 text-emerald-400"
                            : session.kernel.execution_state === "busy"
                            ? "bg-amber-900/30 text-amber-400"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {session.kernel.execution_state}
                      </span>
                      <span className="font-mono text-[10px] text-slate-500">
                        {session.kernel.name}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* File list */}
          <div className="space-y-2">
            {items.length === 0 && !loading && (
              <div className="card text-center">
                <BookOpen
                  size={32}
                  className="mx-auto mb-3 text-slate-600"
                />
                <p className="text-sm text-slate-400">
                  No notebooks found in this directory
                </p>
              </div>
            )}

            {items
              .sort((a, b) => {
                if (a.type === "directory" && b.type !== "directory") return -1;
                if (a.type !== "directory" && b.type === "directory") return 1;
                return a.name.localeCompare(b.name);
              })
              .map((item) => {
                const session = getSessionForPath(item.path);
                return (
                  <button
                    key={item.path}
                    onClick={() =>
                      item.type === "directory"
                        ? navigateToDir(item)
                        : openNotebook(item)
                    }
                    className="card group flex w-full items-center gap-4 text-left transition-colors hover:border-accent/30"
                  >
                    {item.type === "directory" ? (
                      <Folder size={20} className="text-blue-400" />
                    ) : (
                      <FileText size={20} className="text-amber-400" />
                    )}
                    <div className="flex-1">
                      <p className="text-sm font-medium text-white group-hover:text-accent">
                        {item.name}
                      </p>
                      <div className="mt-0.5 flex items-center gap-3 text-xs text-slate-500">
                        <span>
                          Modified: {formatDate(item.last_modified)}
                        </span>
                        {item.size != null && item.size > 0 && (
                          <span>{formatSize(item.size)}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {session && (
                        <span className="flex items-center gap-1 rounded-full bg-emerald-900/30 px-2 py-0.5 text-[10px] text-emerald-400">
                          <CheckCircle2 size={10} />
                          Running
                        </span>
                      )}
                      {item.type === "notebook" && (
                        <a
                          href={`${jupyterBaseUrl}/lab/tree/${item.path}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-400 opacity-0 transition-all hover:border-accent hover:text-accent group-hover:opacity-100"
                          aria-label="Open in JupyterLab"
                        >
                          <ExternalLink size={12} />
                        </a>
                      )}
                      <ChevronRight
                        size={16}
                        className="text-slate-600 group-hover:text-slate-400"
                      />
                    </div>
                  </button>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function NotebooksPage() {
  return (
    <CodeExecGuard feature="Notebooks">
      <Suspense>
        <NotebooksPageInner />
      </Suspense>
    </CodeExecGuard>
  );
}
