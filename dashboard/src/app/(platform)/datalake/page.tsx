// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowUp,
  Check,
  ChevronRight,
  Copy,
  FileJson,
  FileText,
  File as FileIcon,
  Folder,
  HardDrive,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import {
  getBuckets,
  getLakeListing,
  getLakeObject,
  type LakeBucket,
  type LakeListing,
  type LakeObjectDetail,
} from "@/lib/api";
import { ErrorCard } from "@/components/error-card";
import { formatBytes, formatDateTime, relativeTime } from "@/lib/format";

/**
 * Read-only browser over the object store (SeaweedFS S3). Location lives in the URL
 * (?bucket=&prefix=&key=) so the Catalog page can link a table's storage location here.
 */

function useLocation() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const loc = {
    bucket: params.get("bucket") ?? "",
    prefix: params.get("prefix") ?? "",
    key: params.get("key") ?? "",
  };
  const go = useCallback(
    (next: { bucket: string; prefix?: string; key?: string }) => {
      const q = new URLSearchParams({ bucket: next.bucket });
      if (next.prefix) q.set("prefix", next.prefix);
      if (next.key) q.set("key", next.key);
      router.push(`${pathname}?${q}`, { scroll: false });
    },
    [router, pathname]
  );
  return [loc, go] as const;
}

function fileIcon(name: string) {
  const lower = name.toLowerCase();
  if (lower.endsWith(".json") || lower.endsWith(".crc")) return FileJson;
  if (/\.(txt|csv|tsv|log|md|ya?ml|xml|sql|py)$/.test(lower)) return FileText;
  return FileIcon;
}

function fileKind(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".parquet") || lower.endsWith(".snappy.parquet")) return "Parquet";
  if (lower.endsWith(".avro")) return "Avro";
  if (lower.endsWith(".orc")) return "ORC";
  if (lower.endsWith(".json")) return "JSON";
  if (lower.endsWith(".crc")) return "Checksum";
  if (lower.endsWith(".csv")) return "CSV";
  const dot = lower.lastIndexOf(".");
  return dot > 0 ? lower.slice(dot + 1).toUpperCase() : "File";
}

/** Recognise table-format layouts at the current folder. */
function detectTableFormat(listing: LakeListing): "Delta" | "Iceberg" | null {
  const names = new Set(listing.folders.map((f) => f.name));
  if (names.has("_delta_log")) return "Delta";
  if (names.has("metadata") && (names.has("data") || listing.objects.length === 0)) {
    return "Iceberg";
  }
  return null;
}

function prettyPreview(key: string, text: string): string {
  const lower = key.toLowerCase();
  if (lower.endsWith(".json") || lower.endsWith(".crc")) {
    try {
      return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      // Delta commit files and .crc are newline-delimited JSON: pretty-print each line.
      const lines = text.split("\n").filter((l) => l.trim());
      try {
        return lines.map((l) => JSON.stringify(JSON.parse(l), null, 2)).join("\n\n");
      } catch {
        return text;
      }
    }
  }
  return text;
}

function CopyInline({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() =>
        navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1200);
        })
      }
      className="rounded p-1 text-slate-500 hover:bg-white/5 hover:text-white"
      aria-label="Copy path"
      title="Copy path"
    >
      {done ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
    </button>
  );
}

function ObjectPanel({
  bucket,
  objectKey,
  onClose,
}: {
  bucket: string;
  objectKey: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<LakeObjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError(null);
    getLakeObject(bucket, objectKey)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : "Failed to load"));
    return () => {
      cancelled = true;
    };
  }, [bucket, objectKey]);

  const name = objectKey.slice(objectKey.lastIndexOf("/") + 1);
  const uri = `s3://${bucket}/${objectKey}`;

  return (
    <aside className="card flex max-h-[calc(100vh-12rem)] min-w-0 flex-col overflow-hidden p-0">
      <div className="flex items-start gap-3 border-b border-white/[0.06] px-5 py-4">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-white" title={name}>
            {name}
          </p>
          <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-500">
            <span className="truncate font-mono" title={uri}>
              {uri}
            </span>
            <CopyInline text={uri} />
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded p-1 text-slate-400 hover:bg-white/5 hover:text-white"
          aria-label="Close preview"
        >
          <X size={16} />
        </button>
      </div>

      {error && <div className="p-5"><ErrorCard message={error} /></div>}
      {!error && !detail && (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={20} className="animate-spin text-slate-500" />
        </div>
      )}
      {detail && (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <dl className="grid grid-cols-2 gap-4 px-5 py-4 text-sm">
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-slate-500">Size</dt>
              <dd className="text-slate-200">{formatBytes(detail.size)}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-slate-500">Type</dt>
              <dd className="text-slate-200">{fileKind(name)}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-slate-500">Modified</dt>
              <dd className="text-slate-200">{formatDateTime(detail.lastModified)}</dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-wider text-slate-500">Content type</dt>
              <dd className="truncate text-slate-200">{detail.contentType || "—"}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-[11px] uppercase tracking-wider text-slate-500">ETag</dt>
              <dd className="truncate font-mono text-xs text-slate-400">{detail.etag || "—"}</dd>
            </div>
          </dl>
          <div className="border-t border-white/[0.06] px-5 py-4">
            <p className="mb-2 text-[11px] uppercase tracking-wider text-slate-500">Preview</p>
            {detail.preview !== null ? (
              <>
                <pre className="max-h-[28rem] overflow-auto rounded-lg border border-white/[0.06] bg-surface-dark p-3 font-mono text-[11px] leading-relaxed text-slate-300">
                  {prettyPreview(detail.key, detail.preview)}
                </pre>
                {detail.previewTruncated && (
                  <p className="mt-2 text-[11px] text-slate-500">Showing the first 64 KB.</p>
                )}
              </>
            ) : (
              <p className="text-xs text-slate-500">
                {detail.size === 0
                  ? "Empty object."
                  : "Binary file — no text preview. Query it through Spark or the Catalog instead."}
              </p>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

function DataLakeBrowser() {
  const [loc, go] = useLocation();
  const [buckets, setBuckets] = useState<LakeBucket[] | null>(null);
  const [bucketsError, setBucketsError] = useState<string | null>(null);
  const [listing, setListing] = useState<LakeListing | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [filter, setFilter] = useState("");
  const [reloadTick, setReloadTick] = useState(0);

  // Buckets; default to the lakehouse bucket when the URL names none.
  useEffect(() => {
    setBucketsError(null);
    getBuckets()
      .then(({ buckets: list, defaultBucket }) => {
        setBuckets(list);
        if (!loc.bucket && list.length > 0) {
          const pick = list.find((b) => b.name === defaultBucket) ?? list[0];
          go({ bucket: pick.name });
        }
      })
      .catch((e) => setBucketsError(e instanceof Error ? e.message : "Failed to load"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadTick]);

  useEffect(() => {
    if (!loc.bucket) return;
    let cancelled = false;
    setLoading(true);
    setListError(null);
    setFilter("");
    getLakeListing(loc.bucket, loc.prefix)
      .then((l) => !cancelled && setListing(l))
      .catch((e) => {
        if (cancelled) return;
        setListing(null);
        setListError(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [loc.bucket, loc.prefix, reloadTick]);

  async function loadMore() {
    if (!listing?.nextToken) return;
    setLoadingMore(true);
    try {
      const more = await getLakeListing(listing.bucket, listing.prefix, listing.nextToken);
      setListing({
        ...more,
        folders: [...listing.folders, ...more.folders],
        objects: [...listing.objects, ...more.objects],
      });
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Failed to load more");
    } finally {
      setLoadingMore(false);
    }
  }

  const segments = loc.prefix ? loc.prefix.replace(/\/$/, "").split("/") : [];
  const parentPrefix = segments.length > 1 ? `${segments.slice(0, -1).join("/")}/` : "";
  const format = listing ? detectTableFormat(listing) : null;

  const q = filter.trim().toLowerCase();
  const folders = useMemo(
    () => (listing?.folders ?? []).filter((f) => !q || f.name.toLowerCase().includes(q)),
    [listing, q]
  );
  const objects = useMemo(
    () => (listing?.objects ?? []).filter((o) => !q || o.name.toLowerCase().includes(q)),
    [listing, q]
  );
  const totalSize = (listing?.objects ?? []).reduce((acc, o) => acc + o.size, 0);
  const currentUri = loc.bucket ? `s3://${loc.bucket}/${loc.prefix}` : "";

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Data Lake</p>
          <h1 className="text-2xl font-bold text-white">Object store</h1>
          <p className="mt-1 text-sm text-slate-400">
            Browse the files behind every table in SeaweedFS (S3). Read-only.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {buckets && buckets.length > 0 && (
            <label className="flex items-center gap-2 rounded-lg border border-white/10 bg-surface px-3 py-1.5 text-xs text-slate-400">
              <HardDrive size={14} />
              <span className="sr-only">Bucket</span>
              <select
                value={loc.bucket}
                onChange={(e) => go({ bucket: e.target.value })}
                className="bg-transparent text-sm text-white outline-none"
              >
                {buckets.map((b) => (
                  <option key={b.name} value={b.name} className="bg-surface">
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            onClick={() => setReloadTick((t) => t + 1)}
            className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/5 hover:text-white"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {bucketsError && (
        <ErrorCard
          message={bucketsError}
          onRetry={() => setReloadTick((t) => t + 1)}
          hint="Check that storage is running: ./lakehouse start storage"
        />
      )}
      {buckets && buckets.length === 0 && (
        <div className="card text-sm text-slate-400">The object store has no buckets yet.</div>
      )}

      {loc.bucket && (
        <>
          {/* Path bar */}
          <div className="card flex flex-wrap items-center gap-2 px-4 py-3">
            <button
              onClick={() => go({ bucket: loc.bucket, prefix: parentPrefix })}
              disabled={!loc.prefix}
              className="rounded p-1 text-slate-400 hover:bg-white/5 hover:text-white disabled:opacity-30"
              aria-label="Up one level"
              title="Up one level"
            >
              <ArrowUp size={16} />
            </button>
            <nav className="flex min-w-0 flex-1 flex-wrap items-center gap-0.5 text-sm" aria-label="Path">
              <button
                onClick={() => go({ bucket: loc.bucket })}
                className="flex items-center gap-1.5 rounded px-1.5 py-0.5 font-medium text-slate-200 hover:bg-white/5"
              >
                <HardDrive size={14} className="text-accent" /> {loc.bucket}
              </button>
              {segments.map((seg, i) => (
                <span key={i} className="flex items-center gap-0.5">
                  <ChevronRight size={14} className="text-slate-600" />
                  <button
                    onClick={() => go({ bucket: loc.bucket, prefix: `${segments.slice(0, i + 1).join("/")}/` })}
                    className={`rounded px-1.5 py-0.5 ${
                      i === segments.length - 1 ? "text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    {seg}
                  </button>
                </span>
              ))}
            </nav>
            {format && (
              <span className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-medium text-accent">
                <Layers size={12} /> {format} table
              </span>
            )}
            <CopyInline text={currentUri} />
          </div>

          <div className={`grid gap-6 ${loc.key ? "xl:grid-cols-[1fr_26rem]" : ""}`}>
            <div className="card min-w-0 overflow-hidden p-0">
              <div className="flex flex-wrap items-center gap-3 border-b border-white/[0.06] px-4 py-3">
                <div className="relative min-w-[12rem] flex-1">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    placeholder="Filter this folder..."
                    className="w-full rounded-md border border-slate-700 bg-surface-dark py-1.5 pl-8 pr-2 text-xs text-white placeholder-slate-500 outline-none focus:border-accent/50"
                  />
                </div>
                {listing && (
                  <span className="text-xs text-slate-500">
                    {listing.folders.length} folder{listing.folders.length === 1 ? "" : "s"} ·{" "}
                    {listing.objects.length} file{listing.objects.length === 1 ? "" : "s"} · {formatBytes(totalSize)}
                    {listing.truncated ? "+" : ""}
                  </span>
                )}
              </div>

              {listError && (
                <div className="p-4">
                  <ErrorCard message={listError} onRetry={() => setReloadTick((t) => t + 1)} />
                </div>
              )}

              {loading && !listing ? (
                <div className="flex items-center justify-center py-20">
                  <Loader2 size={22} className="animate-spin text-slate-500" />
                </div>
              ) : (
                listing && (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr>
                          <th className="table-header">Name</th>
                          <th className="table-header">Type</th>
                          <th className="table-header text-right">Size</th>
                          <th className="table-header">Modified</th>
                        </tr>
                      </thead>
                      <tbody>
                        {folders.map((f) => (
                          <tr
                            key={f.prefix}
                            onClick={() => go({ bucket: loc.bucket, prefix: f.prefix })}
                            className="cursor-pointer border-t border-white/[0.04] hover:bg-white/[0.03]"
                          >
                            <td className="table-cell">
                              <span className="flex items-center gap-2 font-medium text-white">
                                <Folder size={16} className="shrink-0 text-amber-300" />
                                {f.name}
                              </span>
                            </td>
                            <td className="table-cell text-slate-500">Folder</td>
                            <td className="table-cell text-right text-slate-500">—</td>
                            <td className="table-cell text-slate-500">—</td>
                          </tr>
                        ))}
                        {objects.map((o) => {
                          const Icon = fileIcon(o.name);
                          const active = loc.key === o.key;
                          return (
                            <tr
                              key={o.key}
                              onClick={() => go({ bucket: loc.bucket, prefix: loc.prefix, key: o.key })}
                              className={`cursor-pointer border-t border-white/[0.04] ${
                                active ? "bg-accent/10" : "hover:bg-white/[0.03]"
                              }`}
                            >
                              <td className="table-cell">
                                <span className="flex items-center gap-2 text-slate-200">
                                  <Icon size={16} className="shrink-0 text-slate-400" />
                                  <span className="max-w-[28rem] truncate" title={o.name}>
                                    {o.name}
                                  </span>
                                </span>
                              </td>
                              <td className="table-cell text-slate-400">{fileKind(o.name)}</td>
                              <td className="table-cell text-right font-mono text-xs text-slate-300">
                                {formatBytes(o.size)}
                              </td>
                              <td className="table-cell text-slate-400" title={formatDateTime(o.lastModified)}>
                                {relativeTime(o.lastModified)}
                              </td>
                            </tr>
                          );
                        })}
                        {folders.length === 0 && objects.length === 0 && (
                          <tr>
                            <td colSpan={4} className="px-4 py-12 text-center text-sm text-slate-500">
                              {q ? "Nothing matches the filter." : "This folder is empty."}
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                    {listing.nextToken && (
                      <div className="border-t border-white/[0.06] p-3 text-center">
                        <button
                          onClick={loadMore}
                          disabled={loadingMore}
                          className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:bg-white/5 disabled:opacity-50"
                        >
                          {loadingMore && <Loader2 size={12} className="animate-spin" />}
                          Load more
                        </button>
                      </div>
                    )}
                  </div>
                )
              )}
            </div>

            {loc.key && (
              <ObjectPanel
                bucket={loc.bucket}
                objectKey={loc.key}
                onClose={() => go({ bucket: loc.bucket, prefix: loc.prefix })}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function DataLakePage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-20">
          <Loader2 size={22} className="animate-spin text-slate-500" />
        </div>
      }
    >
      <DataLakeBrowser />
    </Suspense>
  );
}
