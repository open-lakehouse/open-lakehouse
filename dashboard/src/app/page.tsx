// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { useEffect, useState } from "react";
import {
  Database,
  FlaskConical,
  HardDrive,
  Share2,
  Layers,
  Cpu,
  BookOpen,
  Radio,
  Workflow,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from "lucide-react";
import ServiceCard from "@/components/service-card";
import Onboarding, { OnboardingResetButton } from "@/components/onboarding";
import type { ServiceHealth } from "@/lib/api";

const services: Omit<ServiceHealth, "status">[] = [
  {
    name: "SeaweedFS",
    url: "/api/health/storage",
    port: 8333,
    description: "S3-compatible object storage",
  },
  {
    name: "Unity Catalog",
    url: "/api/uc/catalogs",
    port: 8080,
    description: "Data governance & catalog",
  },
  {
    name: "MLflow",
    url: "/api/health/mlflow",
    port: 5000,
    description: "Experiment tracking & model registry",
  },
  {
    name: "Delta Sharing",
    url: "/api/health/delta-sharing",
    port: 8443,
    description: "External data sharing (optional service)",
  },
  {
    name: "Spark 4.1",
    url: "/api/health/spark",
    port: 8082,
    description: "Compute — standalone master + Connect",
  },
  {
    name: "Airflow",
    url: "/api/health/airflow",
    port: 8085,
    description: "Orchestration (optional service)",
  },
  {
    name: "AI Gateway",
    url: "/api/health/ai-gateway",
    port: 5001,
    description: "MLflow AI Gateway (optional service)",
  },
];

const features = [
  { icon: Database, label: "Unity Catalog", detail: "Three-level namespace governance", url: "http://localhost:3001", port: 3001 },
  { icon: Layers, label: "Delta Lake + Iceberg", detail: "ACID transactions, time travel", url: null, port: null },
  { icon: FlaskConical, label: "MLflow", detail: "Experiments, models, observability", url: "http://localhost:5000", port: 5000 },
  { icon: Cpu, label: "Spark 4.1", detail: "Connect-first compute (sc://localhost:15002)", url: "http://localhost:8082", port: 8082 },
  { icon: HardDrive, label: "SeaweedFS Storage", detail: "S3-compatible, self-hosted", url: null, port: null },
  { icon: Share2, label: "Delta Sharing", detail: "Secure external data sharing (optional)", url: "/sharing", port: null },
  { icon: Radio, label: "Kafka", detail: "Event streaming (TCP 9092 — no web UI)", url: null, port: 9092 },
  { icon: Workflow, label: "Airflow", detail: "Workflow orchestration (optional)", url: "http://localhost:8085", port: 8085 },
];

export default function Dashboard() {
  const [health, setHealth] = useState<ServiceHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchitecture, setShowArchitecture] = useState(false);

  useEffect(() => {
    async function check() {
      const results = await Promise.all(
        services.map(async (svc) => {
          try {
            const res = await fetch(svc.url, {
              signal: AbortSignal.timeout(3000),
            });
            return {
              ...svc,
              status: res.ok ? ("healthy" as const) : ("unhealthy" as const),
            };
          } catch {
            return { ...svc, status: "unknown" as const };
          }
        })
      );
      setHealth(results);
      setLoading(false);
    }
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  const healthyCount = health.filter((s) => s.status === "healthy").length;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="hero-glow -mx-8 -mt-8 px-8 pb-6 pt-8">
        <p className="eyebrow">Open Lakehouse</p>
        <h1 className="text-3xl font-bold tracking-tight text-white">Platform Dashboard</h1>
        <p className="mt-1 text-sm text-slate-400">
          Read-only viewer for the open-lakehouse platform
        </p>
        <div className="mt-4 h-1 w-24 rounded-full brand-gradient" />
      </div>

      {/* Onboarding */}
      <Onboarding allServicesHealthy={!loading && healthyCount === services.length} />

      {/* Status summary */}
      <div className="card flex items-center gap-4">
        <div
          className={`h-3 w-3 rounded-full ${
            loading
              ? "animate-pulse bg-amber-400"
              : healthyCount === services.length
                ? "bg-emerald-400"
                : healthyCount > 0
                  ? "bg-amber-400"
                  : "bg-red-400"
          }`}
        />
        <span className="text-sm text-slate-300">
          {loading
            ? "Checking services..."
            : `${healthyCount} of ${services.length} services healthy`}
        </span>
      </div>

      {/* Service health cards */}
      <section>
        <p className="eyebrow">Health</p>
        <h2 className="mb-4 text-lg font-semibold text-white">Services</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {loading
            ? services.map((svc) => (
                <div key={svc.name} className="card animate-pulse">
                  <div className="h-16 rounded bg-slate-800" />
                </div>
              ))
            : health.map((svc) => (
                <ServiceCard key={svc.name} service={svc} />
              ))}
        </div>
      </section>

      {/* Platform capabilities */}
      <section>
        <p className="eyebrow">The Stack</p>
        <h2 className="mb-4 text-lg font-semibold text-white">
          Platform Components
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => {
            const inner = (
              <>
                <span className="icon-badge">
                  <f.icon size={18} />
                </span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-white group-hover:text-accent">
                    {f.label}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-400">{f.detail}</p>
                </div>
                {f.port && (
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[11px] text-slate-500">
                      :{f.port}
                    </span>
                    <ExternalLink size={12} className="text-slate-600 group-hover:text-accent" />
                  </div>
                )}
              </>
            );

            return f.url ? (
              <a
                key={f.label}
                href={f.url}
                target="_blank"
                rel="noopener noreferrer"
                className="card group flex items-start gap-3 transition-colors hover:border-accent/30"
              >
                {inner}
              </a>
            ) : (
              <div
                key={f.label}
                className="card group flex items-start gap-3 transition-colors hover:border-slate-700"
              >
                {inner}
              </div>
            );
          })}
        </div>
      </section>

      {/* Architecture */}
      <section>
        <button
          onClick={() => setShowArchitecture(!showArchitecture)}
          className="mb-4 flex w-full items-center justify-between"
        >
          <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
            <BookOpen size={20} className="text-accent" />
            Architecture Overview
          </h2>
          {showArchitecture ? (
            <ChevronUp size={18} className="text-slate-500" />
          ) : (
            <ChevronDown size={18} className="text-slate-500" />
          )}
        </button>

        {showArchitecture && (
          <div className="space-y-4">
            <div className="card">
              <div className="rounded-lg border border-slate-800 bg-surface-dark p-5">
                <pre className="font-mono text-xs leading-relaxed text-slate-300">
{`Spark 4.1 (Connect server, sc://localhost:15002)
 │
Unity Catalog OSS (governance, port 8080)
 │
Delta Lake / Iceberg (table formats)
 │
SeaweedFS (S3-compatible storage, port 8333)
 │
MLflow (experiment tracking & model registry, port 5000)
Delta Sharing (external sharing, port 8443 — optional)`}
                </pre>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="card">
                <p className="text-sm font-medium text-white">Compute</p>
                <p className="mt-1 text-xs text-slate-400">
                  Spark 4.1 runs Connect-first — clients connect to the Spark Connect
                  server at <span className="font-mono text-emerald-300">sc://localhost:15002</span>.
                </p>
              </div>
              <div className="card">
                <p className="text-sm font-medium text-white">Storage</p>
                <p className="mt-1 text-xs text-slate-400">
                  All data is stored in SeaweedFS at <span className="font-mono text-emerald-300">s3a://lakehouse/</span>,
                  persisted in the <span className="font-mono text-emerald-300">seaweedfs-data</span> volume.
                </p>
              </div>
              <div className="card">
                <p className="text-sm font-medium text-white">Table Formats</p>
                <p className="mt-1 text-xs text-slate-400">
                  Both Delta Lake and Iceberg are supported. ACID transactions, time travel,
                  and schema evolution on object storage.
                </p>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Quick links */}
      <section>
        <p className="eyebrow">Shortcuts</p>
        <h2 className="mb-4 text-lg font-semibold text-white">Quick Access</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "Jupyter Notebook", url: "http://localhost:8889", port: 8889 },
            { label: "Spark UI", url: "http://localhost:8082", port: 8082 },
            { label: "MLflow UI", url: "http://localhost:5000", port: 5000 },
            { label: "Unity Catalog API", url: "http://localhost:8081/api/2.1/unity-catalog/catalogs", port: 8081 },
            { label: "Airflow UI", url: "http://localhost:8085", port: 8085 },
          ].map((link) => (
            <a
              key={link.label}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer"
              className="card group flex items-center justify-between transition-colors hover:border-accent/30"
            >
              <span className="text-sm text-slate-300 group-hover:text-white">
                {link.label}
              </span>
              <span className="font-mono text-[11px] text-slate-500">
                :{link.port}
              </span>
            </a>
          ))}
        </div>
      </section>

      {/* Footer with onboarding reset */}
      <div className="flex justify-center pt-2 pb-4">
        <OnboardingResetButton />
      </div>
    </div>
  );
}
