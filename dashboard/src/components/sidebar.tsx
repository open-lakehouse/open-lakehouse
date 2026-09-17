// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Database,
  FlaskConical,
  HardDrive,
  Share2,
  Workflow,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  type LucideIcon,
} from "lucide-react";
import { useState, useEffect } from "react";

type NavItem = { href: string; label: string; icon: LucideIcon; guarded?: boolean };

// Items marked `guarded` drive code-execution features and are hidden unless
// DASHBOARD_ALLOW_CODE_EXECUTION is on (D6 / T-3.8).
const nav: NavItem[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/catalog", label: "Catalog", icon: Database },
  { href: "/experiments", label: "Experiments", icon: FlaskConical },
  { href: "/pipelines", label: "Pipelines", icon: Workflow, guarded: true },
  { href: "/notebooks", label: "Notebooks", icon: BookOpen, guarded: true },
  { href: "/storage", label: "Storage", icon: HardDrive },
  { href: "/sharing", label: "Sharing", icon: Share2 },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [codeExec, setCodeExec] = useState(false);

  useEffect(() => {
    fetch("/api/features")
      .then((r) => r.json())
      .then((d) => setCodeExec(!!d.codeExecution))
      .catch(() => setCodeExec(false));
  }, []);

  const visibleNav = nav.filter((item) => !item.guarded || codeExec);

  return (
    <aside
      className={`flex h-screen flex-col border-r border-white/[0.06] bg-surface transition-all duration-200 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      <div className="flex h-14 items-center gap-2 border-b border-white/[0.06] px-4">
        <div className="h-7 w-7 shrink-0 rounded-lg brand-gradient" />
        {!collapsed && (
          <span className="text-sm font-bold tracking-tight text-white">
            Open Lakehouse
          </span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="ml-auto rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      <nav className="flex-1 space-y-1 px-2 py-4">
        {visibleNav.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                active
                  ? "bg-accent/10 text-accent"
                  : "text-slate-400 hover:bg-white/5 hover:text-white"
              }`}
            >
              <item.icon size={18} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-white/[0.06] px-4 py-3">
        {!collapsed && (
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Open-Source Lakehouse
          </p>
        )}
      </div>
    </aside>
  );
}
