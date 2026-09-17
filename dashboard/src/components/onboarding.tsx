// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Rocket, X, CheckCircle2, Circle, ExternalLink } from "lucide-react";

const STORAGE_KEY = "lakehouse-onboarding-dismissed";

interface OnboardingProps {
  allServicesHealthy: boolean;
}

interface Step {
  label: string;
  detail: string;
  done: boolean;
  href?: string;
  external?: boolean;
}

export function OnboardingResetButton() {
  return (
    <button
      onClick={() => {
        localStorage.removeItem(STORAGE_KEY);
        window.dispatchEvent(new Event("storage"));
      }}
      className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
    >
      Show getting started guide
    </button>
  );
}

export default function Onboarding({ allServicesHealthy }: OnboardingProps) {
  const [dismissed, setDismissed] = useState(true); // default hidden to avoid flash

  useEffect(() => {
    setDismissed(localStorage.getItem(STORAGE_KEY) === "true");

    function onStorage() {
      setDismissed(localStorage.getItem(STORAGE_KEY) === "true");
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  function dismiss() {
    localStorage.setItem(STORAGE_KEY, "true");
    setDismissed(true);
  }

  if (dismissed) return null;

  const steps: Step[] = [
    {
      label: "All services are running",
      detail: "Platform health checks are passing",
      done: allServicesHealthy,
    },
    {
      label: "Open Jupyter & run a starter notebook",
      detail: "Launch Jupyter to create your first table",
      href: "http://localhost:8889",
      external: true,
      done: false,
    },
    {
      label: "Browse the Data Catalog",
      detail: "Explore schemas, tables, and metadata in Unity Catalog",
      href: "/catalog",
      done: false,
    },
    {
      label: "Track an ML Experiment",
      detail: "View experiment runs and logged models in MLflow",
      href: "/experiments",
      done: false,
    },
    {
      label: "Explore OpenSharing",
      detail: "See how data is shared externally via the open protocol",
      href: "/sharing",
      done: false,
    },
  ];

  return (
    <div className="card relative border-accent/20">
      <button
        onClick={dismiss}
        className="absolute right-4 top-4 rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-white transition-colors"
        title="Dismiss"
      >
        <X size={16} />
      </button>

      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10">
          <Rocket size={20} className="text-accent" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-white">Getting Started</h2>
          <p className="text-xs text-slate-400">
            Follow these steps to explore your lakehouse platform
          </p>
        </div>
      </div>

      <ol className="space-y-3">
        {steps.map((step, i) => {
          const content = (
            <li
              key={i}
              className={`flex items-start gap-3 rounded-lg px-3 py-2 transition-colors ${
                step.href ? "hover:bg-slate-800/50" : ""
              }`}
            >
              {step.done ? (
                <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-emerald-400" />
              ) : (
                <Circle size={18} className="mt-0.5 shrink-0 text-slate-600" />
              )}
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${step.done ? "text-emerald-300" : "text-slate-200"}`}>
                  <span className="text-slate-500 mr-1.5">{i + 1}.</span>
                  {step.label}
                  {step.external && (
                    <ExternalLink size={12} className="inline ml-1.5 text-slate-500" />
                  )}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">{step.detail}</p>
              </div>
            </li>
          );

          if (step.href && step.external) {
            return (
              <a key={i} href={step.href} target="_blank" rel="noopener noreferrer" className="block">
                {content}
              </a>
            );
          }
          if (step.href) {
            return (
              <Link key={i} href={step.href} className="block">
                {content}
              </Link>
            );
          }
          return <div key={i}>{content}</div>;
        })}
      </ol>

      <div className="mt-4 flex justify-end">
        <button
          onClick={dismiss}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          Got it, hide this
        </button>
      </div>
    </div>
  );
}
