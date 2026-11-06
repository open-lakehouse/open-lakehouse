// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Home,
  Database,
  HardDrive,
  CalendarClock,
  FlaskConical,
  Share2,
  Workflow,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  LogOut,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { useState, useEffect } from "react";
import { getSessionUser, logout } from "@/lib/api";

type NavItem = { href: string; label: string; icon: LucideIcon; guarded?: boolean };

const primaryNav: NavItem[] = [
  { href: "/home", label: "Home", icon: Home },
  { href: "/catalog", label: "Catalog", icon: Database },
  { href: "/datalake", label: "Data Lake", icon: HardDrive },
  { href: "/jobs", label: "Jobs", icon: CalendarClock },
];

// Items marked `guarded` drive code-execution features and are hidden unless
// DASHBOARD_ALLOW_CODE_EXECUTION is on (D6 / T-3.8).
const moreNav: NavItem[] = [
  { href: "/experiments", label: "Experiments", icon: FlaskConical },
  { href: "/sharing", label: "Sharing", icon: Share2 },
  { href: "/pipelines", label: "Pipelines", icon: Workflow, guarded: true },
  { href: "/notebooks", label: "Notebooks", icon: BookOpen, guarded: true },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [codeExec, setCodeExec] = useState(false);
  const [user, setUser] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/features")
      .then((r) => r.json())
      .then((d) => setCodeExec(!!d.codeExecution))
      .catch(() => setCodeExec(false));
    getSessionUser().then(setUser);
  }, []);

  async function signOut() {
    await logout();
    router.replace("/");
    router.refresh();
  }

  const renderItem = (item: NavItem) => {
    const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
    return (
      <Link
        key={item.href}
        href={item.href}
        title={collapsed ? item.label : undefined}
        aria-current={active ? "page" : undefined}
        className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
          active
            ? "bg-accent/10 text-accent"
            : "text-slate-400 hover:bg-white/5 hover:text-white"
        }`}
      >
        <item.icon size={18} className="shrink-0" />
        {!collapsed && <span>{item.label}</span>}
      </Link>
    );
  };

  return (
    <aside
      className={`flex h-screen shrink-0 flex-col border-r border-white/[0.06] bg-surface transition-all duration-200 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      <div className="flex h-14 items-center gap-2 border-b border-white/[0.06] px-4">
        <Link href="/home" className="flex min-w-0 items-center gap-2">
          <div className="h-7 w-7 shrink-0 rounded-lg brand-gradient" />
          {!collapsed && (
            <span className="truncate text-sm font-bold tracking-tight text-white">
              Open Lakehouse
            </span>
          )}
        </Link>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="ml-auto rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-2 py-4">
        {primaryNav.map(renderItem)}
        <div className="px-3 pb-1 pt-5">
          {!collapsed ? (
            <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
              More
            </p>
          ) : (
            <div className="border-t border-white/[0.06]" />
          )}
        </div>
        {moreNav.filter((i) => !i.guarded || codeExec).map(renderItem)}
      </nav>

      <div className="border-t border-white/[0.06] p-2">
        {!collapsed && user && (
          <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate-400">
            <UserRound size={14} className="shrink-0" />
            <span className="truncate">{user}</span>
          </div>
        )}
        <button
          onClick={signOut}
          title={collapsed ? "Sign out" : undefined}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-400 transition-colors hover:bg-white/5 hover:text-white"
        >
          <LogOut size={18} className="shrink-0" />
          {!collapsed && <span>Sign out</span>}
        </button>
      </div>
    </aside>
  );
}
