// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Database,
  FolderOpen,
  HardDrive,
  Info,
  Loader2,
  RefreshCw,
  Search,
  Table2,
} from "lucide-react";
import {
  dataLakeHref,
  getCatalogs,
  getSchemas,
  getTable,
  getTables,
  type Catalog,
  type Schema,
  type Table,
} from "@/lib/api";
import { ErrorCard } from "@/components/error-card";
import { formatDateTime } from "@/lib/format";

/**
 * Warehouse catalog explorer over Unity Catalog OSS: catalogs → schemas → tables.
 * Selection lives in the URL (?c=&s=&t=) so other pages can deep-link here.
 */

type Selection = { c?: string; s?: string; t?: string };

type Loadable<T> = { state: "loading" } | { state: "error"; error: string } | { state: "ok"; data: T };

function useSelection(): [Selection, (next: Selection) => void] {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const sel: Selection = {
    c: params.get("c") ?? undefined,
    s: params.get("s") ?? undefined,
    t: params.get("t") ?? undefined,
  };
  const set = useCallback(
    (next: Selection) => {
      const q = new URLSearchParams();
      if (next.c) q.set("c", next.c);
      if (next.c && next.s) q.set("s", next.s);
      if (next.c && next.s && next.t) q.set("t", next.t);
      const qs = q.toString();
      router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname]
  );
  return [sel, set];
}

function errMsg(e: unknown) {
  return e instanceof Error ? e.message : "Failed to load";
}

// ---------------------------------------------------------------- tree

function TreeRow({
  depth,
  icon,
  label,
  active,
  expandable,
  expanded,
  loading,
  onToggle,
  onSelect,
}: {
  depth: number;
  icon: React.ReactNode;
  label: string;
  active: boolean;
  expandable: boolean;
  expanded?: boolean;
  loading?: boolean;
  onToggle?: () => void;
  onSelect: () => void;
}) {
  return (
    <div
      className={`group flex items-center rounded-md pr-2 text-sm ${
        active ? "bg-accent/10 text-accent" : "text-slate-300 hover:bg-white/5"
      }`}
      style={{ paddingLeft: depth * 14 + 4 }}
    >
      <button
        type="button"
        onClick={onToggle}
        disabled={!expandable}
        aria-label={expanded ? `Collapse ${label}` : `Expand ${label}`}
        className={`flex h-7 w-5 shrink-0 items-center justify-center text-slate-500 ${
          expandable ? "hover:text-white" : "invisible"
        }`}
      >
        {loading ? (
          <Loader2 size={12} className="animate-spin" />
        ) : expanded ? (
          <ChevronDown size={14} />
        ) : (
          <ChevronRight size={14} />
        )}
      </button>
      <button
        type="button"
        onClick={onSelect}
        className="flex min-w-0 flex-1 items-center gap-2 py-1.5 text-left"
        title={label}
      >
        {icon}
        <span className="truncate">{label}</span>
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- detail bits

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1200);
        });
      }}
      className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-white"
      aria-label="Copy"
      title="Copy"
    >
      {done ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wider text-slate-500">{label}</p>
      <div className="mt-0.5 break-words text-sm text-slate-200">{children}</div>
    </div>
  );
}

function Badge({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "accent" | "emerald" | "amber" }) {
  const tones = {
    slate: "bg-white/5 text-slate-300",
    accent: "bg-accent/15 text-accent",
    emerald: "bg-emerald-400/10 text-emerald-300",
    amber: "bg-amber-400/10 text-amber-300",
  } as const;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

function PropertiesTable({ properties }: { properties?: Record<string, string> }) {
  const entries = Object.entries(properties ?? {});
  if (entries.length === 0) return <p className="px-6 py-4 text-sm text-slate-500">No properties.</p>;
  return (
    <table className="w-full">
      <thead>
        <tr>
          <th className="table-header">Key</th>
          <th className="table-header">Value</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-t border-white/[0.04]">
            <td className="table-cell font-mono text-xs text-slate-400">{k}</td>
            <td className="table-cell whitespace-normal break-all font-mono text-xs">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 size={22} className="animate-spin text-slate-500" />
    </div>
  );
}

// ---------------------------------------------------------------- detail panes

function Overview({
  catalogs,
  onSelect,
}: {
  catalogs: Catalog[];
  onSelect: (s: Selection) => void;
}) {
  return (
    <div className="space-y-6">
      <div className="card flex gap-3 border-accent/20 bg-accent/5">
        <Info size={18} className="mt-0.5 shrink-0 text-accent" />
        <div className="text-sm text-slate-300">
          <p>
            The warehouse is governed by <span className="text-white">Unity Catalog OSS</span>. Tables
            are addressed with a three-level name:{" "}
            <span className="font-mono text-blue-300">catalog</span>
            <span className="text-slate-500">.</span>
            <span className="font-mono text-amber-300">schema</span>
            <span className="text-slate-500">.</span>
            <span className="font-mono text-emerald-300">table</span>
          </p>
          <p className="mt-1 text-xs text-slate-400">
            From Spark: <code className="font-mono text-slate-300">spark.table(&quot;unity.&lt;schema&gt;.&lt;table&gt;&quot;)</code>.
            Managed Delta tables live under <code className="font-mono text-slate-300">s3://lakehouse/</code>.
          </p>
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-white">Catalogs ({catalogs.length})</h2>
        {catalogs.length === 0 ? (
          <div className="card text-sm text-slate-400">
            No catalogs yet. Create one with Spark SQL, e.g.{" "}
            <code className="font-mono text-slate-300">CREATE SCHEMA unity.demo</code>.
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {catalogs.map((c) => (
              <button
                key={c.name}
                onClick={() => onSelect({ c: c.name })}
                className="card group flex items-start gap-3 text-left transition-colors hover:border-accent/40"
              >
                <Database size={18} className="mt-0.5 text-blue-300" />
                <div className="min-w-0">
                  <p className="font-medium text-white group-hover:text-accent">{c.name}</p>
                  <p className="mt-0.5 truncate text-xs text-slate-400">{c.comment || "No description"}</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CatalogDetail({
  catalog,
  schemas,
  onSelect,
}: {
  catalog: Catalog | undefined;
  name: string;
  schemas: Loadable<Schema[]>;
  onSelect: (s: Selection) => void;
}) {
  return (
    <div className="space-y-6">
      {catalog && (
        <div className="card grid gap-4 sm:grid-cols-3">
          <Field label="Description">{catalog.comment || "—"}</Field>
          <Field label="Owner">{catalog.owner || "—"}</Field>
          <Field label="Created">{formatDateTime(catalog.created_at)}</Field>
        </div>
      )}
      <div className="card overflow-hidden p-0">
        <div className="flex items-center gap-2 border-b border-white/[0.06] px-6 py-4">
          <FolderOpen size={16} className="text-amber-300" />
          <h3 className="text-sm font-semibold text-white">
            Schemas{schemas.state === "ok" ? ` (${schemas.data.length})` : ""}
          </h3>
        </div>
        {schemas.state === "loading" && <Spinner />}
        {schemas.state === "error" && <p className="px-6 py-4 text-sm text-red-300">{schemas.error}</p>}
        {schemas.state === "ok" &&
          (schemas.data.length === 0 ? (
            <p className="px-6 py-4 text-sm text-slate-500">No schemas in this catalog.</p>
          ) : (
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-header">Name</th>
                  <th className="table-header">Description</th>
                  <th className="table-header">Created</th>
                </tr>
              </thead>
              <tbody>
                {schemas.data.map((s) => (
                  <tr
                    key={s.name}
                    onClick={() => onSelect({ c: s.catalog_name, s: s.name })}
                    className="cursor-pointer border-t border-white/[0.04] hover:bg-white/[0.03]"
                  >
                    <td className="table-cell font-medium text-white">{s.name}</td>
                    <td className="table-cell max-w-xs truncate text-slate-400">{s.comment || "—"}</td>
                    <td className="table-cell text-slate-400">{formatDateTime(s.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
      </div>
    </div>
  );
}

function SchemaDetail({
  schema,
  tables,
  onSelect,
}: {
  schema: Schema | undefined;
  tables: Loadable<Table[]>;
  onSelect: (s: Selection) => void;
}) {
  return (
    <div className="space-y-6">
      {schema && (
        <div className="card grid gap-4 sm:grid-cols-3">
          <Field label="Description">{schema.comment || "—"}</Field>
          <Field label="Owner">{schema.owner || "—"}</Field>
          <Field label="Created">{formatDateTime(schema.created_at)}</Field>
        </div>
      )}
      <div className="card overflow-hidden p-0">
        <div className="flex items-center gap-2 border-b border-white/[0.06] px-6 py-4">
          <Table2 size={16} className="text-emerald-300" />
          <h3 className="text-sm font-semibold text-white">
            Tables{tables.state === "ok" ? ` (${tables.data.length})` : ""}
          </h3>
        </div>
        {tables.state === "loading" && <Spinner />}
        {tables.state === "error" && <p className="px-6 py-4 text-sm text-red-300">{tables.error}</p>}
        {tables.state === "ok" &&
          (tables.data.length === 0 ? (
            <p className="px-6 py-4 text-sm text-slate-500">No tables in this schema.</p>
          ) : (
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-header">Name</th>
                  <th className="table-header">Type</th>
                  <th className="table-header">Format</th>
                  <th className="table-header">Created</th>
                </tr>
              </thead>
              <tbody>
                {tables.data.map((t) => (
                  <tr
                    key={t.name}
                    onClick={() => onSelect({ c: t.catalog_name, s: t.schema_name, t: t.name })}
                    className="cursor-pointer border-t border-white/[0.04] hover:bg-white/[0.03]"
                  >
                    <td className="table-cell font-medium text-white">{t.name}</td>
                    <td className="table-cell">
                      <Badge>{t.table_type}</Badge>
                    </td>
                    <td className="table-cell">
                      {t.data_source_format ? <Badge tone="emerald">{t.data_source_format}</Badge> : "—"}
                    </td>
                    <td className="table-cell text-slate-400">{formatDateTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
      </div>
    </div>
  );
}

function TableDetail({ table }: { table: Loadable<Table> }) {
  const [tab, setTab] = useState<"columns" | "details" | "properties">("columns");
  if (table.state === "loading") return <Spinner />;
  if (table.state === "error") return <ErrorCard message={table.error} />;

  const t = table.data;
  const fullName = `${t.catalog_name}.${t.schema_name}.${t.name}`;
  const lakeHref = dataLakeHref(t.storage_location);
  const columns = [...(t.columns ?? [])].sort((a, b) => a.position - b.position);

  return (
    <div className="space-y-6">
      <div className="card space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{t.table_type}</Badge>
          {t.data_source_format && <Badge tone="emerald">{t.data_source_format}</Badge>}
          <span className="ml-auto flex items-center gap-1 font-mono text-xs text-slate-400">
            {fullName}
            <CopyButton text={fullName} />
          </span>
        </div>
        {t.comment && <p className="text-sm text-slate-300">{t.comment}</p>}
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Columns">{columns.length}</Field>
          <Field label="Owner">{t.owner || "—"}</Field>
          <Field label="Last updated">{formatDateTime(t.updated_at ?? t.created_at)}</Field>
        </div>
        {t.storage_location && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-white/[0.06] bg-surface-dark px-3 py-2">
            <HardDrive size={14} className="shrink-0 text-slate-500" />
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-300" title={t.storage_location}>
              {t.storage_location}
            </span>
            {lakeHref && (
              <Link href={lakeHref} className="text-xs font-medium text-accent hover:underline">
                Browse files
              </Link>
            )}
          </div>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <div className="flex gap-1 border-b border-white/[0.06] px-4">
          {(["columns", "details", "properties"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`-mb-px border-b-2 px-3 py-3 text-sm capitalize ${
                tab === k
                  ? "border-accent text-white"
                  : "border-transparent text-slate-400 hover:text-white"
              }`}
            >
              {k}
            </button>
          ))}
        </div>

        {tab === "columns" &&
          (columns.length === 0 ? (
            <p className="px-6 py-4 text-sm text-slate-500">No column metadata registered.</p>
          ) : (
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-header w-12">#</th>
                  <th className="table-header">Name</th>
                  <th className="table-header">Type</th>
                  <th className="table-header">Nullable</th>
                  <th className="table-header">Comment</th>
                </tr>
              </thead>
              <tbody>
                {columns.map((col) => (
                  <tr key={`${col.position}-${col.name}`} className="border-t border-white/[0.04]">
                    <td className="table-cell font-mono text-slate-500">{col.position}</td>
                    <td className="table-cell font-medium text-white">{col.name}</td>
                    <td className="table-cell font-mono text-xs text-blue-300">{col.type_text}</td>
                    <td className="table-cell">
                      <span className={`text-xs ${col.nullable ? "text-slate-500" : "text-amber-300"}`}>
                        {col.nullable ? "yes" : "no"}
                      </span>
                    </td>
                    <td className="table-cell max-w-xs truncate text-slate-400">{col.comment || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}

        {tab === "details" && (
          <div className="grid gap-5 p-6 sm:grid-cols-2">
            <Field label="Full name">
              <span className="font-mono text-xs">{fullName}</span>
            </Field>
            <Field label="Table ID">
              <span className="font-mono text-xs">{t.table_id || "—"}</span>
            </Field>
            <Field label="Created">{formatDateTime(t.created_at)}</Field>
            <Field label="Updated">{formatDateTime(t.updated_at)}</Field>
            <Field label="Read from Spark">
              <code className="font-mono text-xs text-emerald-300">spark.table(&quot;{fullName}&quot;)</code>
            </Field>
            <Field label="Read with SQL">
              <code className="font-mono text-xs text-emerald-300">SELECT * FROM {fullName} LIMIT 10</code>
            </Field>
          </div>
        )}

        {tab === "properties" && <PropertiesTable properties={t.properties} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- page

function CatalogExplorer() {
  const [sel, select] = useSelection();
  const [filter, setFilter] = useState("");
  const [catalogs, setCatalogs] = useState<Loadable<Catalog[]>>({ state: "loading" });
  const [schemas, setSchemas] = useState<Record<string, Loadable<Schema[]>>>({});
  const [tables, setTables] = useState<Record<string, Loadable<Table[]>>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<Loadable<Table>>({ state: "loading" });

  const loadCatalogs = useCallback(async () => {
    setCatalogs({ state: "loading" });
    setSchemas({});
    setTables({});
    try {
      setCatalogs({ state: "ok", data: await getCatalogs() });
    } catch (e) {
      setCatalogs({ state: "error", error: errMsg(e) });
    }
  }, []);

  const loadSchemas = useCallback(async (c: string) => {
    setSchemas((m) => ({ ...m, [c]: { state: "loading" } }));
    try {
      const data = await getSchemas(c);
      setSchemas((m) => ({ ...m, [c]: { state: "ok", data } }));
    } catch (e) {
      setSchemas((m) => ({ ...m, [c]: { state: "error", error: errMsg(e) } }));
    }
  }, []);

  const loadTables = useCallback(async (c: string, s: string) => {
    const k = `${c}.${s}`;
    setTables((m) => ({ ...m, [k]: { state: "loading" } }));
    try {
      const data = await getTables(c, s);
      setTables((m) => ({ ...m, [k]: { state: "ok", data } }));
    } catch (e) {
      setTables((m) => ({ ...m, [k]: { state: "error", error: errMsg(e) } }));
    }
  }, []);

  useEffect(() => {
    loadCatalogs();
  }, [loadCatalogs]);

  // Keep the tree in step with the URL selection (deep links, back/forward).
  useEffect(() => {
    if (catalogs.state !== "ok") return;
    if (sel.c) {
      setExpanded((e) => new Set(e).add(sel.c as string));
      if (!schemas[sel.c]) loadSchemas(sel.c);
    }
    if (sel.c && sel.s) {
      const k = `${sel.c}.${sel.s}`;
      setExpanded((e) => new Set(e).add(k));
      if (!tables[k]) loadTables(sel.c, sel.s);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel.c, sel.s, catalogs.state]);

  useEffect(() => {
    if (!(sel.c && sel.s && sel.t)) return;
    let cancelled = false;
    setDetail({ state: "loading" });
    getTable(`${sel.c}.${sel.s}.${sel.t}`)
      .then((data) => !cancelled && setDetail({ state: "ok", data }))
      .catch((e) => !cancelled && setDetail({ state: "error", error: errMsg(e) }));
    return () => {
      cancelled = true;
    };
  }, [sel.c, sel.s, sel.t]);

  function toggle(key: string, load: () => void, loaded: boolean) {
    setExpanded((e) => {
      const next = new Set(e);
      if (next.has(key)) next.delete(key);
      else {
        next.add(key);
        if (!loaded) load();
      }
      return next;
    });
  }

  const q = filter.trim().toLowerCase();
  const matches = (name: string) => !q || name.toLowerCase().includes(q);

  const currentCatalog = useMemo(
    () => (catalogs.state === "ok" ? catalogs.data.find((c) => c.name === sel.c) : undefined),
    [catalogs, sel.c]
  );
  const currentSchemas = sel.c ? schemas[sel.c] ?? { state: "loading" as const } : undefined;
  const currentSchema =
    currentSchemas?.state === "ok" ? currentSchemas.data.find((s) => s.name === sel.s) : undefined;
  const currentTables = sel.c && sel.s ? tables[`${sel.c}.${sel.s}`] ?? { state: "loading" as const } : undefined;

  const crumbs: { label: string; to: Selection }[] = [{ label: "Catalog", to: {} }];
  if (sel.c) crumbs.push({ label: sel.c, to: { c: sel.c } });
  if (sel.c && sel.s) crumbs.push({ label: sel.s, to: { c: sel.c, s: sel.s } });
  if (sel.c && sel.s && sel.t) crumbs.push({ label: sel.t, to: sel });

  const title = sel.t ?? sel.s ?? sel.c ?? "Warehouse catalog";
  const TitleIcon = sel.t ? Table2 : sel.s ? FolderOpen : Database;

  return (
    <div className="mx-auto flex h-full max-w-7xl flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Catalog</p>
          <h1 className="text-2xl font-bold text-white">Warehouse catalog</h1>
          <p className="mt-1 text-sm text-slate-400">
            Catalogs, schemas and tables registered in Unity Catalog OSS.
          </p>
        </div>
        <button
          onClick={loadCatalogs}
          className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5 hover:text-white"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="grid min-h-0 flex-1 gap-6 lg:grid-cols-[18rem_1fr]">
        {/* Tree */}
        <aside className="card flex max-h-[calc(100vh-12rem)] flex-col p-3">
          <div className="relative mb-3">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter loaded objects..."
              className="w-full rounded-md border border-slate-700 bg-surface-dark py-1.5 pl-8 pr-2 text-xs text-white placeholder-slate-500 outline-none focus:border-accent/50"
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {catalogs.state === "loading" && <Spinner />}
            {catalogs.state === "error" && (
              <p className="px-2 py-3 text-xs text-red-300">Unity Catalog unavailable.</p>
            )}
            {catalogs.state === "ok" && catalogs.data.length === 0 && (
              <p className="px-2 py-3 text-xs text-slate-500">No catalogs.</p>
            )}
            {catalogs.state === "ok" &&
              catalogs.data.map((c) => {
                const cs = schemas[c.name];
                const cOpen = expanded.has(c.name);
                const schemaRows =
                  cs?.state === "ok"
                    ? cs.data.filter(
                        (s) =>
                          matches(s.name) ||
                          (tables[`${c.name}.${s.name}`]?.state === "ok" &&
                            (tables[`${c.name}.${s.name}`] as { data: Table[] }).data.some((t) => matches(t.name)))
                      )
                    : [];
                if (q && !matches(c.name) && schemaRows.length === 0) return null;
                return (
                  <div key={c.name}>
                    <TreeRow
                      depth={0}
                      icon={<Database size={14} className="shrink-0 text-blue-300" />}
                      label={c.name}
                      active={sel.c === c.name && !sel.s}
                      expandable
                      expanded={cOpen}
                      loading={cs?.state === "loading"}
                      onToggle={() => toggle(c.name, () => loadSchemas(c.name), !!cs)}
                      onSelect={() => select({ c: c.name })}
                    />
                    {cOpen && cs?.state === "error" && (
                      <p className="py-1 pl-10 text-xs text-red-300">{cs.error}</p>
                    )}
                    {cOpen && cs?.state === "ok" && cs.data.length === 0 && (
                      <p className="py-1 pl-10 text-xs text-slate-500">No schemas</p>
                    )}
                    {cOpen &&
                      (q && !matches(c.name) ? schemaRows : cs?.state === "ok" ? cs.data : []).map((s) => {
                        const k = `${c.name}.${s.name}`;
                        const ts = tables[k];
                        const sOpen = expanded.has(k);
                        const tableRows =
                          ts?.state === "ok"
                            ? ts.data.filter((t) => !q || matches(t.name) || matches(s.name) || matches(c.name))
                            : [];
                        return (
                          <div key={k}>
                            <TreeRow
                              depth={1}
                              icon={<FolderOpen size={14} className="shrink-0 text-amber-300" />}
                              label={s.name}
                              active={sel.c === c.name && sel.s === s.name && !sel.t}
                              expandable
                              expanded={sOpen}
                              loading={ts?.state === "loading"}
                              onToggle={() => toggle(k, () => loadTables(c.name, s.name), !!ts)}
                              onSelect={() => select({ c: c.name, s: s.name })}
                            />
                            {sOpen && ts?.state === "error" && (
                              <p className="py-1 pl-14 text-xs text-red-300">{ts.error}</p>
                            )}
                            {sOpen && ts?.state === "ok" && ts.data.length === 0 && (
                              <p className="py-1 pl-14 text-xs text-slate-500">No tables</p>
                            )}
                            {sOpen &&
                              tableRows.map((t) => (
                                <TreeRow
                                  key={t.name}
                                  depth={2}
                                  icon={<Table2 size={14} className="shrink-0 text-emerald-300" />}
                                  label={t.name}
                                  active={sel.c === c.name && sel.s === s.name && sel.t === t.name}
                                  expandable={false}
                                  onSelect={() => select({ c: c.name, s: s.name, t: t.name })}
                                />
                              ))}
                          </div>
                        );
                      })}
                  </div>
                );
              })}
          </div>
        </aside>

        {/* Detail */}
        <section className="min-w-0 space-y-5">
          <nav className="flex flex-wrap items-center gap-1 text-sm" aria-label="Breadcrumb">
            {crumbs.map((c, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <ChevronRight size={14} className="text-slate-600" />}
                <button
                  onClick={() => select(c.to)}
                  className={`rounded px-1.5 py-0.5 ${
                    i === crumbs.length - 1 ? "text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  {c.label}
                </button>
              </span>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/5">
              <TitleIcon size={18} className={sel.t ? "text-emerald-300" : sel.s ? "text-amber-300" : "text-blue-300"} />
            </span>
            <h2 className="truncate text-xl font-semibold text-white">{title}</h2>
          </div>

          {catalogs.state === "error" ? (
            <ErrorCard
              message={catalogs.error}
              onRetry={loadCatalogs}
              hint="Check that Unity Catalog is running: ./lakehouse start unity-catalog"
            />
          ) : catalogs.state === "loading" ? (
            <Spinner />
          ) : sel.c && sel.s && sel.t ? (
            <TableDetail key={`${sel.c}.${sel.s}.${sel.t}`} table={detail} />
          ) : sel.c && sel.s ? (
            <SchemaDetail schema={currentSchema} tables={currentTables!} onSelect={select} />
          ) : sel.c ? (
            <CatalogDetail catalog={currentCatalog} name={sel.c} schemas={currentSchemas!} onSelect={select} />
          ) : (
            <Overview catalogs={catalogs.data} onSelect={select} />
          )}
        </section>
      </div>
    </div>
  );
}

export default function CatalogPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <CatalogExplorer />
    </Suspense>
  );
}
