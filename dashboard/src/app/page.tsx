// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Database, HardDrive, CalendarClock, Loader2, Lock, AlertTriangle } from "lucide-react";

const highlights = [
  { icon: Database, label: "Catalog", detail: "Unity Catalog OSS — catalogs, schemas, tables" },
  { icon: HardDrive, label: "Data Lake", detail: "Browse the SeaweedFS object store" },
  { icon: CalendarClock, label: "Jobs", detail: "Airflow DAGs and their recent runs" },
];

function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next === "/") return "/home";
  return next;
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [configured, setConfigured] = useState(true);

  useEffect(() => {
    fetch("/api/auth/session")
      .then((r) => r.json())
      .then((d) => {
        if (d.user) router.replace(next);
        setConfigured(d.loginConfigured !== false);
      })
      .catch(() => {});
  }, [next, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error || `Sign-in failed (${res.status})`);
        setSubmitting(false);
        return;
      }
      router.replace(next);
      router.refresh();
    } catch {
      setError("Could not reach the server");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-sm space-y-5">
      <div>
        <h2 className="text-2xl font-bold text-white">Sign in</h2>
        <p className="mt-1 text-sm text-slate-400">Use your platform operator account.</p>
      </div>

      {!configured && (
        <div className="flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>
            Login is not configured yet. Set <code className="font-mono">DASHBOARD_PASSWORD</code>{" "}
            in <code className="font-mono">.env</code> and restart with{" "}
            <code className="font-mono">./lakehouse start dashboard</code>.
          </span>
        </div>
      )}

      <label className="block">
        <span className="text-xs font-medium text-slate-300">Username</span>
        <input
          type="text"
          autoComplete="username"
          autoFocus
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="mt-1.5 w-full rounded-lg border border-slate-700 bg-surface-dark px-3 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30"
          placeholder="admin"
        />
      </label>

      <label className="block">
        <span className="text-xs font-medium text-slate-300">Password</span>
        <input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1.5 w-full rounded-lg border border-slate-700 bg-surface-dark px-3 py-2.5 text-sm text-white placeholder-slate-500 outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30"
        />
      </label>

      {error && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="btn-primary flex w-full items-center justify-center gap-2 py-2.5 disabled:opacity-60"
      >
        {submitting ? <Loader2 size={16} className="animate-spin" /> : <Lock size={16} />}
        {submitting ? "Signing in..." : "Sign in"}
      </button>

      <p className="text-center text-[11px] text-slate-500">
        Credentials come from <code className="font-mono">DASHBOARD_USERNAME</code> /{" "}
        <code className="font-mono">DASHBOARD_PASSWORD</code>.
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="hero-glow relative hidden flex-col justify-between border-r border-white/[0.06] p-12 lg:flex">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl brand-gradient" />
          <span className="text-lg font-bold tracking-tight text-white">Open Lakehouse</span>
        </div>

        <div className="max-w-md">
          <p className="eyebrow">Unified data platform</p>
          <h1 className="text-4xl font-bold leading-tight tracking-tight text-white">
            Your lakehouse, <span className="brand-gradient-text">one place</span>.
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-slate-400">
            Spark, Unity Catalog, Delta &amp; Iceberg, Airflow, MLflow and SeaweedFS — open
            source, running on your machine, behind one interface.
          </p>
          <ul className="mt-8 space-y-4">
            {highlights.map((h) => (
              <li key={h.label} className="flex items-start gap-3">
                <span className="icon-badge">
                  <h.icon size={18} />
                </span>
                <div>
                  <p className="text-sm font-medium text-white">{h.label}</p>
                  <p className="text-xs text-slate-400">{h.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-[11px] uppercase tracking-widest text-slate-600">
          Open-source lakehouse · self-hosted
        </p>
      </section>

      <section className="flex flex-col items-center justify-center p-8">
        <div className="mb-10 flex items-center gap-3 lg:hidden">
          <div className="h-8 w-8 rounded-xl brand-gradient" />
          <span className="text-lg font-bold tracking-tight text-white">Open Lakehouse</span>
        </div>
        <Suspense fallback={<Loader2 size={20} className="animate-spin text-slate-500" />}>
          <LoginForm />
        </Suspense>
      </section>
    </div>
  );
}
