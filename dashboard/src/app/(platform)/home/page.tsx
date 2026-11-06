// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  CalendarClock,
  Cpu,
  Database,
  ExternalLink,
  FlaskConical,
  HardDrive,
  Network,
  Radio,
  RefreshCw,
  Share2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { getSessionUser } from "@/lib/api";

type Status = "healthy" | "unhealthy" | "unknown" | "checking";

interface Module {
  href: string;
  label: string;
  icon: LucideIcon;
  description: string;
  backend: string;
  /** Endpoint whose 2xx means "this module's backend is up". */
  probe: string;
  /** Optional count shown on the card. */
  count?: { url: string; pick: (data: unknown) => number | null; noun: string };
}

const workspace: Module[] = [
  {
    href: "/catalog",
    label: "Catalog",
    icon: Database,
    description: "Explore the warehouse: catalogs, schemas, tables and their columns.",
    backend: "Unity Catalog OSS",
    probe: "/api/uc/catalogs",
    count: {
      url: "/api/uc/catalogs",
      pick: (d) => (d as { catalogs?: unknown[] }).catalogs?.length ?? 0,
      noun: "catalog",
    },
  },
  {
    href: "/datalake",
    label: "Data Lake",
    icon: HardDrive,
    description: "Browse buckets, folders and files in the object store.",
    backend: "SeaweedFS (S3)",
    probe: "/api/health/storage",
    count: {
      url: "/api/datalake/buckets",
      pick: (d) => (d as { buckets?: unknown[] }).buckets?.length ?? 0,
      noun: "bucket",
    },
  },
  {
    href: "/jobs",
    label: "Jobs",
    icon: CalendarClock,
    description: "See every Airflow DAG, its schedule and recent runs.",
    backend: "Airflow 3.1",
    probe: "/api/health/airflow",
    count: {
      url: "/api/airflow/dags?limit=1",
      pick: (d) => (d as { total_entries?: number }).total_entries ?? null,
      noun: "job",
    },
  },
];

const moreModules: Module[] = [
  {
    href: "/experiments",
    label: "Experiments",
    icon: FlaskConical,
    description: "MLflow experiments and runs.",
    backend: "MLflow",
    probe: "/api/health/mlflow",
  },
  {
    href: "/sharing",
    label: "Sharing",
    icon: Share2,
    description: "Delta Sharing shares, schemas and tables.",
    backend: "Delta Sharing (optional)",
    probe: "/api/health/delta-sharing",
  },
];

interface Service {
  name: string;
  icon: LucideIcon;
  role: string;
  endpoint: string;
  probe: string | null;
  url: string | null;
}

const services: Service[] = [
  { name: "Spark 4.1", icon: Cpu, role: "Compute (Connect at sc://localhost:15002)", endpoint: ":8082", probe: "/api/health/spark", url: "http://localhost:8082" },
  { name: "Unity Catalog", icon: Database, role: "Catalog & governance (REST)", endpoint: ":8081", probe: "/api/uc/catalogs", url: "http://localhost:8081/api/2.1/unity-catalog/catalogs" },
  { name: "SeaweedFS", icon: HardDrive, role: "S3-compatible object store", endpoint: ":8333", probe: "/api/health/storage", url: null },
  { name: "Airflow", icon: CalendarClock, role: "Orchestration", endpoint: ":8085", probe: "/api/health/airflow", url: "http://localhost:8085" },
  { name: "MLflow", icon: FlaskConical, role: "Tracking & model registry", endpoint: ":5000", probe: "/api/health/mlflow", url: "http://localhost:5000" },
  { name: "AI Gateway", icon: Sparkles, role: "MLflow AI Gateway (optional)", endpoint: ":5001", probe: "/api/health/ai-gateway", url: null },
  { name: "Delta Sharing", icon: Share2, role: "External data sharing (optional)", endpoint: ":8443", probe: "/api/health/delta-sharing", url: null },
  { name: "Kafka", icon: Radio, role: "Event streaming (no web UI)", endpoint: ":9092", probe: null, url: null },
  { name: "Jupyter", icon: Network, role: "Notebooks (optional)", endpoint: ":8889", probe: null, url: "http://localhost:8889" },
];

async function probe(url: string): Promise<Status> {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(4000) });
    // Health routes report their verdict in the body: "unknown" means the service
    // isn't reachable (not started), and Delta Sharing answers 200
    // {"status":"unconfigured"} when no token is set.
    const body = await res.json().catch(() => null);
    const reported = body && typeof body === "object" ? (body as { status?: unknown }).status : undefined;
    if (reported === "unknown" || reported === "unconfigured") return "unknown";
    if (!res.ok || reported === "unhealthy") return "unhealthy";
    return "healthy";
  } catch {
    return "unknown";
  }
}

const dotClass: Record<Status, string> = {
  healthy: "bg-emerald-400",
  unhealthy: "bg-red-400",
  unknown: "bg-slate-500",
  checking: "animate-pulse bg-amber-400",
};

const statusLabel: Record<Status, string> = {
  healthy: "Online",
  unhealthy: "Unavailable",
  unknown: "Not running",
  checking: "Checking",
};

function StatusPill({ status }: { status: Status }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white/5 px-2 py-0.5 text-[11px] font-medium text-slate-300">
      <span className={`h-1.5 w-1.5 rounded-full ${dotClass[status]}`} />
      {statusLabel[status]}
    </span>
  );
}

export default function HomePage() {
  const [user, setUser] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [counts, setCounts] = useState<Record<string, number | null>>({});
  const [refreshing, setRefreshing] = useState(false);

  async function refresh() {
    setRefreshing(true);
    const probes = Array.from(
      new Set([...workspace, ...moreModules].map((m) => m.probe).concat(
        services.map((s) => s.probe).filter((p): p is string => !!p)
      ))
    );
    setStatus(Object.fromEntries(probes.map((p) => [p, "checking" as Status])));

    const countJobs = workspace.map(async (m) => {
      if (!m.count) return;
      try {
        const res = await fetch(m.count.url, { signal: AbortSignal.timeout(6000) });
        const value = res.ok ? m.count.pick(await res.json()) : null;
        setCounts((c) => ({ ...c, [m.href]: value }));
      } catch {
        setCounts((c) => ({ ...c, [m.href]: null }));
      }
    });
    const probeJobs = probes.map(async (p) => {
      const s = await probe(p);
      setStatus((prev) => ({ ...prev, [p]: s }));
    });
    await Promise.all([...countJobs, ...probeJobs]);
    setRefreshing(false);
  }

  useEffect(() => {
    getSessionUser().then(setUser);
    refresh();
    const id = setInterval(refresh, 60000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const probed = services.filter((s) => s.probe);
  const online = probed.filter((s) => status[s.probe as string] === "healthy").length;
  const checking = probed.some((s) => (status[s.probe as string] ?? "checking") === "checking");

  return (
    <div className="mx-auto max-w-6xl space-y-10">
      <div className="hero-glow -mx-8 -mt-8 px-8 pb-8 pt-10">
        <p className="eyebrow">Open Lakehouse</p>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white">
              Welcome{user ? `, ${user}` : ""}
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Everything in your local lakehouse, in one place.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-surface/70 px-3 py-1.5 text-xs text-slate-300">
              <span
                className={`h-2 w-2 rounded-full ${
                  checking
                    ? "animate-pulse bg-amber-400"
                    : online === probed.length
                      ? "bg-emerald-400"
                      : online > 0
                        ? "bg-amber-400"
                        : "bg-red-400"
                }`}
              />
              {checking ? "Checking services..." : `${online} of ${probed.length} services online`}
            </span>
            <button
              onClick={refresh}
              disabled={refreshing}
              aria-label="Refresh status"
              className="rounded-lg border border-white/10 p-2 text-slate-400 hover:bg-white/5 hover:text-white disabled:opacity-50"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
        <div className="mt-5 h-1 w-24 rounded-full brand-gradient" />
      </div>

      <section>
        <p className="eyebrow">Workspace</p>
        <h2 className="mb-4 text-lg font-semibold text-white">Start here</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {workspace.map((m) => {
            const count = counts[m.href];
            return (
              <Link
                key={m.href}
                href={m.href}
                className="card group flex flex-col gap-4 transition-colors hover:border-accent/40"
              >
                <div className="flex items-start justify-between">
                  <span className="icon-badge h-11 w-11">
                    <m.icon size={20} />
                  </span>
                  <StatusPill status={status[m.probe] ?? "checking"} />
                </div>
                <div className="flex-1">
                  <h3 className="text-base font-semibold text-white group-hover:text-accent">
                    {m.label}
                  </h3>
                  <p className="mt-1 text-sm text-slate-400">{m.description}</p>
                </div>
                <div className="flex items-center justify-between border-t border-white/[0.06] pt-3 text-xs">
                  <span className="text-slate-500">{m.backend}</span>
                  <span className="flex items-center gap-1 text-slate-300">
                    {m.count && typeof count === "number"
                      ? `${count} ${m.count.noun}${count === 1 ? "" : "s"}`
                      : "Open"}
                    <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {moreModules.map((m) => (
            <Link
              key={m.href}
              href={m.href}
              className="card group flex items-center gap-4 py-4 transition-colors hover:border-accent/40"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/5 text-slate-300 group-hover:text-accent">
                <m.icon size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-white group-hover:text-accent">{m.label}</p>
                <p className="truncate text-xs text-slate-400">{m.description}</p>
              </div>
              <StatusPill status={status[m.probe] ?? "checking"} />
            </Link>
          ))}
        </div>
      </section>

      <section>
        <p className="eyebrow">Directory</p>
        <h2 className="mb-4 text-lg font-semibold text-white">Platform services</h2>
        <div className="card overflow-hidden p-0">
          <ul className="divide-y divide-white/[0.06]">
            {services.map((s) => {
              const st: Status = s.probe ? (status[s.probe] ?? "checking") : "unknown";
              return (
                <li key={s.name} className="flex flex-wrap items-center gap-4 px-6 py-4">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/5 text-slate-300">
                    <s.icon size={18} />
                  </span>
                  <div className="min-w-[10rem] flex-1">
                    <p className="text-sm font-medium text-white">{s.name}</p>
                    <p className="text-xs text-slate-400">{s.role}</p>
                  </div>
                  <span className="w-16 font-mono text-xs text-slate-500">{s.endpoint}</span>
                  <div className="w-28">
                    {s.probe ? (
                      <StatusPill status={st} />
                    ) : (
                      <span className="text-[11px] text-slate-500">No health probe</span>
                    )}
                  </div>
                  <div className="w-24 text-right">
                    {s.url ? (
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                      >
                        Open UI <ExternalLink size={12} />
                      </a>
                    ) : (
                      <span className="text-xs text-slate-600">—</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          Optional services show as “Not running” until started, e.g.{" "}
          <code className="font-mono text-slate-400">./lakehouse start airflow</code>.
        </p>
      </section>
    </div>
  );
}
