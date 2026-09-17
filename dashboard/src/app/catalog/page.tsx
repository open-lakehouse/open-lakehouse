// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Database,
  FolderOpen,
  Table2,
  ChevronRight,
  Columns3,
  Loader2,
  Search,
  Info,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { getCatalogs, getSchemas, getTables, getTable } from "@/lib/api";
import type { Catalog, Schema, Table, Column } from "@/lib/api";
import { ErrorCard } from "@/components/error-card";

type View =
  | { level: "catalogs" }
  | { level: "schemas"; catalog: string }
  | { level: "tables"; catalog: string; schema: string }
  | { level: "detail"; catalog: string; schema: string; table: string };

export default function CatalogPage() {
  const [view, setView] = useState<View>({ level: "catalogs" });
  const [catalogs, setCatalogs] = useState<Catalog[]>([]);
  const [schemas, setSchemas] = useState<Schema[]>([]);
  const [tables, setTables] = useState<Table[]>([]);
  const [detail, setDetail] = useState<Table | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNamespaceInfo, setShowNamespaceInfo] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSearchQuery("");

    try {
      switch (view.level) {
        case "catalogs":
          setCatalogs(await getCatalogs());
          break;
        case "schemas":
          setSchemas(await getSchemas(view.catalog));
          break;
        case "tables":
          setTables(await getTables(view.catalog, view.schema));
          break;
        case "detail":
          setDetail(
            await getTable(`${view.catalog}.${view.schema}.${view.table}`)
          );
          break;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const breadcrumbs: { label: string; action: () => void }[] = [
    { label: "Catalogs", action: () => setView({ level: "catalogs" }) },
  ];
  if (view.level !== "catalogs") {
    breadcrumbs.push({
      label: (view as { catalog: string }).catalog,
      action: () =>
        setView({
          level: "schemas",
          catalog: (view as { catalog: string }).catalog,
        }),
    });
  }
  if (view.level === "tables" || view.level === "detail") {
    breadcrumbs.push({
      label: (view as { schema: string }).schema,
      action: () =>
        setView({
          level: "tables",
          catalog: (view as { catalog: string }).catalog,
          schema: (view as { schema: string }).schema,
        }),
    });
  }
  if (view.level === "detail") {
    breadcrumbs.push({
      label: (view as { table: string }).table,
      action: () => {},
    });
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Data Catalog</h1>
        <p className="mt-1 text-sm text-slate-400">
          Browse Unity Catalog&apos;s three-level namespace
        </p>
      </div>

      {/* Three-Level Namespace explainer */}
      <button
        onClick={() => setShowNamespaceInfo(!showNamespaceInfo)}
        className="card flex w-full items-center gap-3 text-left transition-colors hover:border-accent/30"
      >
        <Info size={18} className="text-accent" />
        <div className="flex-1">
          <p className="text-sm font-medium text-white">
            Three-Level Namespace
          </p>
          <p className="mt-0.5 text-xs text-slate-400">
            <span className="font-mono text-blue-300">catalog</span>
            <span className="text-slate-600"> . </span>
            <span className="font-mono text-amber-300">schema</span>
            <span className="text-slate-600"> . </span>
            <span className="font-mono text-emerald-300">table</span>
          </p>
        </div>
        {showNamespaceInfo ? (
          <ChevronUp size={16} className="text-slate-500" />
        ) : (
          <ChevronDown size={16} className="text-slate-500" />
        )}
      </button>

      {showNamespaceInfo && (
        <div className="card space-y-4 border-accent/20 bg-accent/5">
          <div className="rounded-lg border border-slate-800 bg-surface-dark p-4">
            <pre className="font-mono text-xs leading-relaxed text-slate-300">
{`catalog.schema.table
   │      │      │
   │      │      └─ Table name (e.g., transactions, products)
   │      └──────── Schema/Database (logical grouping)
   └─────────────── Catalog (data source)`}
            </pre>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-800/50 p-3">
              <p className="text-xs font-medium text-white">Automatic storage</p>
              <p className="mt-1 text-xs text-slate-400">
                Tables are stored in SeaweedFS at <code className="text-emerald-300">s3a://lakehouse/warehouse/</code> — no manual LOCATION needed.
              </p>
            </div>
            <div className="rounded-lg border border-slate-800/50 p-3">
              <p className="text-xs font-medium text-white">Consistent namespace</p>
              <p className="mt-1 text-xs text-slate-400">
                The same namespace works across Spark SQL, PySpark, and any engine that supports Unity Catalog.
              </p>
            </div>
            <div className="rounded-lg border border-slate-800/50 p-3">
              <p className="text-xs font-medium text-white">Governance ready</p>
              <p className="mt-1 text-xs text-slate-400">
                Centralized metadata, lineage, and access control for every data asset.
              </p>
            </div>
            <div className="rounded-lg border border-slate-800/50 p-3">
              <p className="text-xs font-medium text-white">Industry standard</p>
              <p className="mt-1 text-xs text-slate-400">
                Compatible with Databricks and modern lakehouse architecture patterns.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Breadcrumbs */}
      <div className="flex items-center gap-1 text-sm">
        {breadcrumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={14} className="text-slate-600" />}
            <button
              onClick={crumb.action}
              className={`rounded px-1.5 py-0.5 ${
                i === breadcrumbs.length - 1
                  ? "text-white"
                  : "text-slate-400 hover:bg-slate-800 hover:text-white"
              }`}
            >
              {crumb.label}
            </button>
          </span>
        ))}
      </div>

      {error && (
        <ErrorCard
          message={error}
          onRetry={fetchData}
          hint="Check if Unity Catalog is running with: ./lakehouse status"
        />
      )}

      {/* Search filter */}
      {!loading && !error && view.level !== "detail" && (
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
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-slate-500" />
        </div>
      ) : (
        <>
          {/* Catalog list */}
          {view.level === "catalogs" && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {catalogs.filter((c) => c.name.toLowerCase().includes(searchQuery.toLowerCase())).map((c) => (
                <button
                  key={c.name}
                  onClick={() =>
                    setView({ level: "schemas", catalog: c.name })
                  }
                  className="card group flex items-start gap-3 text-left transition-colors hover:border-accent/30"
                >
                  <Database
                    size={18}
                    className="mt-0.5 text-accent"
                  />
                  <div>
                    <p className="text-sm font-medium text-white group-hover:text-accent">
                      {c.name}
                    </p>
                    {c.comment && (
                      <p className="mt-1 text-xs text-slate-400">
                        {c.comment}
                      </p>
                    )}
                  </div>
                </button>
              ))}
              {catalogs.filter((c) => c.name.toLowerCase().includes(searchQuery.toLowerCase())).length === 0 && (
                <p className="col-span-full text-sm text-slate-500">
                  No catalogs found
                </p>
              )}
            </div>
          )}

          {/* Schema list */}
          {view.level === "schemas" && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {schemas.filter((s) => s.name.toLowerCase().includes(searchQuery.toLowerCase())).map((s) => (
                <button
                  key={s.name}
                  onClick={() =>
                    setView({
                      level: "tables",
                      catalog: (view as { catalog: string }).catalog,
                      schema: s.name,
                    })
                  }
                  className="card group flex items-start gap-3 text-left transition-colors hover:border-accent/30"
                >
                  <FolderOpen
                    size={18}
                    className="mt-0.5 text-amber-400"
                  />
                  <div>
                    <p className="text-sm font-medium text-white group-hover:text-accent">
                      {s.name}
                    </p>
                    {s.comment && (
                      <p className="mt-1 text-xs text-slate-400">
                        {s.comment}
                      </p>
                    )}
                  </div>
                </button>
              ))}
              {schemas.filter((s) => s.name.toLowerCase().includes(searchQuery.toLowerCase())).length === 0 && (
                <p className="col-span-full text-sm text-slate-500">
                  No schemas found
                </p>
              )}
            </div>
          )}

          {/* Table list */}
          {view.level === "tables" && (
            <div className="space-y-2">
              {tables.filter((t) => t.name.toLowerCase().includes(searchQuery.toLowerCase())).map((t) => (
                <button
                  key={t.name}
                  onClick={() =>
                    setView({
                      level: "detail",
                      catalog: (view as { catalog: string }).catalog,
                      schema: (view as { schema: string }).schema,
                      table: t.name,
                    })
                  }
                  className="card group flex w-full items-center gap-4 text-left transition-colors hover:border-accent/30"
                >
                  <Table2 size={18} className="text-emerald-400" />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-white group-hover:text-accent">
                      {t.name}
                    </p>
                    <p className="text-xs text-slate-500">
                      {t.table_type}
                      {t.data_source_format
                        ? ` \u00b7 ${t.data_source_format}`
                        : ""}
                    </p>
                  </div>
                  <ChevronRight
                    size={16}
                    className="text-slate-600 group-hover:text-slate-400"
                  />
                </button>
              ))}
              {tables.filter((t) => t.name.toLowerCase().includes(searchQuery.toLowerCase())).length === 0 && (
                <p className="text-sm text-slate-500">No tables found</p>
              )}
            </div>
          )}

          {/* Table detail */}
          {view.level === "detail" && detail && (
            <div className="space-y-6">
              <div className="card">
                <h2 className="text-lg font-semibold text-white">
                  {detail.name}
                </h2>
                <div className="mt-3 grid gap-4 text-sm sm:grid-cols-3">
                  <div>
                    <span className="text-slate-500">Type</span>
                    <p className="text-slate-300">{detail.table_type}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Format</span>
                    <p className="text-slate-300">
                      {detail.data_source_format ?? "—"}
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-500">Location</span>
                    <p className="truncate font-mono text-xs text-slate-400">
                      {detail.storage_location ?? "—"}
                    </p>
                  </div>
                </div>
              </div>

              {detail.columns && detail.columns.length > 0 && (
                <div className="card overflow-hidden p-0">
                  <div className="flex items-center gap-2 border-b border-slate-800 px-6 py-4">
                    <Columns3 size={16} className="text-accent" />
                    <h3 className="text-sm font-semibold text-white">
                      Columns ({detail.columns.length})
                    </h3>
                  </div>
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-slate-800/50">
                        <th className="table-header">#</th>
                        <th className="table-header">Name</th>
                        <th className="table-header">Type</th>
                        <th className="table-header">Nullable</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.columns.map((col: Column) => (
                        <tr
                          key={col.position}
                          className="border-b border-slate-800/30 hover:bg-slate-800/30"
                        >
                          <td className="table-cell font-mono text-slate-500">
                            {col.position}
                          </td>
                          <td className="table-cell font-medium text-white">
                            {col.name}
                          </td>
                          <td className="table-cell font-mono text-xs text-blue-300">
                            {col.type_text}
                          </td>
                          <td className="table-cell">
                            <span
                              className={`text-xs ${
                                col.nullable
                                  ? "text-slate-500"
                                  : "text-amber-400"
                              }`}
                            >
                              {col.nullable ? "yes" : "no"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
