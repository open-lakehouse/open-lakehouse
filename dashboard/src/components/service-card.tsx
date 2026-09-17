// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { Activity, AlertCircle, HelpCircle } from "lucide-react";
import type { ServiceHealth } from "@/lib/api";

const statusConfig = {
  healthy: {
    icon: Activity,
    color: "text-emerald-400",
    bg: "bg-emerald-400/10",
    label: "Healthy",
  },
  unhealthy: {
    icon: AlertCircle,
    color: "text-red-400",
    bg: "bg-red-400/10",
    label: "Unhealthy",
  },
  unknown: {
    icon: HelpCircle,
    color: "text-slate-500",
    bg: "bg-slate-500/10",
    label: "Unknown",
  },
};

export default function ServiceCard({ service }: { service: ServiceHealth }) {
  const cfg = statusConfig[service.status];
  const Icon = cfg.icon;

  return (
    <div className="card flex items-start gap-4">
      <div className={`rounded-lg p-2.5 ${cfg.bg}`}>
        <Icon size={20} className={cfg.color} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">{service.name}</h3>
          <span
            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${cfg.bg} ${cfg.color}`}
          >
            {cfg.label}
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-400">{service.description}</p>
        <p className="mt-2 font-mono text-[11px] text-slate-500">
          :{service.port}
        </p>
      </div>
    </div>
  );
}
