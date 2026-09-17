// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, Lock } from "lucide-react";

/**
 * Wraps a page that drives code-execution / write features (Pipelines,
 * Notebooks). When DASHBOARD_ALLOW_CODE_EXECUTION is off (the default) it hides
 * the page behind a disabled notice; when on, it renders the page with a
 * persistent warning banner. The authoritative gate is server-side on the API
 * routes — this is the matching UI treatment (D6 / T-3.8).
 */
export default function CodeExecGuard({
  feature,
  children,
}: {
  feature: string;
  children: ReactNode;
}) {
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    fetch("/api/features")
      .then((r) => r.json())
      .then((d) => setEnabled(!!d.codeExecution))
      .catch(() => setEnabled(false));
  }, []);

  if (enabled === null) return null; // brief loading flash

  if (!enabled) {
    return (
      <div className="mx-auto max-w-3xl">
        <div className="card flex items-start gap-3 border-amber-900/50 bg-amber-950/30 text-amber-200">
          <Lock size={18} className="mt-0.5 shrink-0" />
          <div>
            <h1 className="mb-1 text-lg font-semibold text-white">
              {feature} is disabled
            </h1>
            <p className="text-sm">
              This page runs code on the platform and is disabled by default. Enable it
              only on a trusted, non-exposed network by starting the dashboard with{" "}
              <code className="rounded bg-slate-800 px-1 py-0.5 text-emerald-300">
                DASHBOARD_ALLOW_CODE_EXECUTION=true
              </code>
              .
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex items-start gap-3 rounded-lg border border-red-900/50 bg-red-950/30 px-4 py-3 text-red-200">
        <AlertTriangle size={18} className="mt-0.5 shrink-0" />
        <p className="text-xs">
          Code-execution is <strong>enabled</strong>. This page can run arbitrary code on
          the platform — do NOT expose this dashboard to an untrusted network.
        </p>
      </div>
      {children}
    </>
  );
}
