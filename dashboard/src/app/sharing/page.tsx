// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import { useEffect, useState } from "react";
import {
  Share2,
  Shield,
  Globe,
  Terminal,
  ExternalLink,
  FolderOpen,
  Table2,
  ChevronRight,
  Loader2,
  AlertCircle,
  Copy,
  Check,
  Code2,
  Network,
} from "lucide-react";
import {
  getShares,
  getShareSchemas,
  getShareTables,
} from "@/lib/api";
import type {
  DeltaShare,
  DeltaShareSchema,
  DeltaShareTable,
} from "@/lib/api";

type ShareView =
  | { level: "shares" }
  | { level: "schemas"; share: string }
  | { level: "tables"; share: string; schema: string };

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
      title="Copy to clipboard"
    >
      {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
    </button>
  );
}

function CodeBlock({ title, language, code }: { title: string; language: string; code: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-surface-dark overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
        <span className="text-xs font-medium text-slate-400">{title}</span>
        <div className="flex items-center gap-2">
          <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] font-mono text-slate-500">
            {language}
          </span>
          <CopyButton text={code} />
        </div>
      </div>
      <pre className="overflow-x-auto p-4 text-xs leading-relaxed text-emerald-300">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export default function SharingPage() {
  const [view, setView] = useState<ShareView>({ level: "shares" });
  const [shares, setShares] = useState<DeltaShare[]>([]);
  const [schemas, setSchemas] = useState<DeltaShareSchema[]>([]);
  const [tables, setTables] = useState<DeltaShareTable[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"browse" | "architecture" | "connect">("browse");

  useEffect(() => {
    setLoading(true);
    setError(null);

    (async () => {
      try {
        switch (view.level) {
          case "shares":
            setShares(await getShares());
            break;
          case "schemas":
            setSchemas(await getShareSchemas(view.share));
            break;
          case "tables":
            setTables(await getShareTables(view.share, view.schema));
            break;
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    })();
  }, [view]);

  const breadcrumbs: { label: string; action: () => void }[] = [
    { label: "Shares", action: () => setView({ level: "shares" }) },
  ];
  if (view.level !== "shares") {
    breadcrumbs.push({
      label: (view as { share: string }).share,
      action: () =>
        setView({ level: "schemas", share: (view as { share: string }).share }),
    });
  }
  if (view.level === "tables") {
    breadcrumbs.push({
      label: (view as { schema: string }).schema,
      action: () => {},
    });
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">OpenSharing</h1>
        <p className="mt-1 text-sm text-slate-400">
          Secure, open protocol for sharing live data without copying
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card flex items-start gap-3">
          <Shield size={18} className="mt-0.5 text-accent" />
          <div>
            <p className="text-sm font-medium text-white">Token Auth</p>
            <p className="mt-1 text-xs text-slate-400">
              Bearer token + HTTPS encryption for all access
            </p>
          </div>
        </div>
        <div className="card flex items-start gap-3">
          <Globe size={18} className="mt-0.5 text-emerald-400" />
          <div>
            <p className="text-sm font-medium text-white">No Data Copying</p>
            <p className="mt-1 text-xs text-slate-400">
              Recipients read directly from your storage
            </p>
          </div>
        </div>
        <div className="card flex items-start gap-3">
          <Share2 size={18} className="mt-0.5 text-purple-400" />
          <div>
            <p className="text-sm font-medium text-white">Open Protocol</p>
            <p className="mt-1 text-xs text-slate-400">
              Works with Databricks, Spark, pandas, PowerBI
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border border-slate-800 bg-surface p-1">
        {[
          { id: "browse" as const, label: "Browse Shares", icon: FolderOpen },
          { id: "architecture" as const, label: "Architecture", icon: Network },
          { id: "connect" as const, label: "Connect", icon: Code2 },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-accent/10 text-accent"
                : "text-slate-400 hover:bg-slate-800 hover:text-white"
            }`}
          >
            <tab.icon size={16} />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Browse Shares tab */}
      {activeTab === "browse" && (
        <div className="space-y-4">
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
            <div className="card flex items-center gap-3 border-red-900/50 bg-red-950/30 text-red-300">
              <AlertCircle size={18} />
              <div>
                <span className="text-sm">{error}</span>
                <p className="mt-1 text-xs text-red-400/70">
                  Make sure the OpenSharing container is running: docker ps | grep delta-sharing
                </p>
              </div>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 size={24} className="animate-spin text-slate-500" />
            </div>
          ) : (
            <>
              {/* Share list */}
              {view.level === "shares" && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {shares.map((s) => (
                    <button
                      key={s.name}
                      onClick={() => setView({ level: "schemas", share: s.name })}
                      className="card group flex items-start gap-3 text-left transition-colors hover:border-accent/30"
                    >
                      <Share2 size={18} className="mt-0.5 text-purple-400" />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-white group-hover:text-accent">
                          {s.name}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          Click to browse schemas and tables
                        </p>
                      </div>
                      <ChevronRight size={16} className="mt-0.5 text-slate-600 group-hover:text-slate-400" />
                    </button>
                  ))}
                  {shares.length === 0 && !error && (
                    <p className="col-span-full text-sm text-slate-500">
                      No shares found. Add tables to your share via{" "}
                      <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-emerald-300">
                        docker/delta-sharing/server.yaml
                      </code>
                    </p>
                  )}
                </div>
              )}

              {/* Schema list */}
              {view.level === "schemas" && (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {schemas.map((s) => (
                    <button
                      key={s.name}
                      onClick={() =>
                        setView({
                          level: "tables",
                          share: (view as { share: string }).share,
                          schema: s.name,
                        })
                      }
                      className="card group flex items-start gap-3 text-left transition-colors hover:border-accent/30"
                    >
                      <FolderOpen size={18} className="mt-0.5 text-amber-400" />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-white group-hover:text-accent">
                          {s.name}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">Schema</p>
                      </div>
                      <ChevronRight size={16} className="mt-0.5 text-slate-600 group-hover:text-slate-400" />
                    </button>
                  ))}
                  {schemas.length === 0 && (
                    <p className="col-span-full text-sm text-slate-500">
                      No schemas in this share
                    </p>
                  )}
                </div>
              )}

              {/* Table list */}
              {view.level === "tables" && (
                <div className="space-y-2">
                  {tables.map((t) => (
                    <div
                      key={t.name}
                      className="card flex items-center gap-4"
                    >
                      <Table2 size={18} className="text-emerald-400" />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-white">
                          {t.name}
                        </p>
                        <p className="mt-0.5 font-mono text-xs text-slate-500">
                          {t.share}.{t.schema}.{t.name}
                        </p>
                      </div>
                      {t.id && (
                        <span className="font-mono text-[11px] text-slate-600">
                          {t.id}
                        </span>
                      )}
                    </div>
                  ))}
                  {tables.length === 0 && (
                    <p className="text-sm text-slate-500">No tables in this schema</p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Architecture tab */}
      {activeTab === "architecture" && (
        <div className="space-y-6">
          <div className="card">
            <h2 className="mb-4 text-sm font-semibold text-white">
              How OpenSharing Works
            </h2>
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Diagram */}
              <div className="rounded-lg border border-slate-800 bg-surface-dark p-6">
                <pre className="font-mono text-xs leading-relaxed text-slate-300">
{`Your Lakehouse                 OpenSharing Client
┌──────────────────┐           ┌───────────────────┐
│  SeaweedFS       │           │   Databricks      │
│  (Delta Tables)  │           │   Spark           │
│       ↓          │           │   Pandas          │
│  OpenSharing     │   HTTPS   │   PowerBI         │
│  Server (API)    │──────────▶│   Any Client      │
│       ↓          │  + Token  │                   │
│  Share Profile   │──────────▶│                   │
└──────────────────┘           └───────────────────┘`}
                </pre>
              </div>

              {/* Key points */}
              <div className="space-y-4">
                <div className="space-y-3">
                  {[
                    {
                      title: "No data copying",
                      desc: "Recipients read directly from your object storage via pre-signed URLs. Data never leaves your infrastructure.",
                    },
                    {
                      title: "Real-time access",
                      desc: "Changes to Delta tables appear immediately for recipients. No ETL pipelines or sync jobs needed.",
                    },
                    {
                      title: "Read-only by design",
                      desc: "Recipients can only read data. They cannot modify, delete, or write to your tables.",
                    },
                    {
                      title: "Pre-signed URL security",
                      desc: "The server generates short-lived pre-signed URLs for each data file, ensuring secure and time-limited access.",
                    },
                  ].map((item) => (
                    <div key={item.title} className="rounded-lg border border-slate-800/50 bg-surface p-3">
                      <p className="text-sm font-medium text-white">{item.title}</p>
                      <p className="mt-1 text-xs text-slate-400">{item.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Server info */}
          <div className="card">
            <h2 className="mb-4 text-sm font-semibold text-white">
              Server Configuration
            </h2>
            <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Endpoint", value: "https://localhost:8443" },
                { label: "Protocol", value: "OpenSharing v1" },
                { label: "Authentication", value: "Bearer token" },
                { label: "Config", value: "docker/delta-sharing/server.yaml" },
              ].map((item) => (
                <div key={item.label}>
                  <span className="text-xs text-slate-500">{item.label}</span>
                  <p className="mt-0.5 font-mono text-xs text-slate-300">
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* External access flow */}
          <div className="card">
            <h2 className="mb-4 text-sm font-semibold text-white">
              External Access
            </h2>
            <p className="mb-4 text-xs text-slate-400">
              To share data outside your network, expose the Delta Sharing server and the
              object store behind a public HTTPS endpoint (a reverse proxy, tunnel, or load
              balancer — provisioning that is out of scope for this repo). A URL re-signing
              proxy rewrites pre-signed S3 URLs to point at that public endpoint.
            </p>
            <div className="rounded-lg border border-slate-800 bg-surface-dark p-4">
              <pre className="font-mono text-xs leading-relaxed text-slate-300">
{`1. ./lakehouse share start   # Start the sharing server + proxy
2. Expose it publicly        # Public HTTPS endpoint (out of scope)
3. Set S3_PUBLIC_ENDPOINT    # Point the proxy at that endpoint
4. Profile generated         # lakehouse.share
5. Upload to recipient       # Share the .share file`}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Connect tab */}
      {activeTab === "connect" && (
        <div className="space-y-6">
          {/* Share profile */}
          <div className="card">
            <h2 className="mb-2 text-sm font-semibold text-white">
              Share Profile
            </h2>
            <p className="mb-4 text-xs text-slate-400">
              A share profile is a JSON file containing the endpoint and credentials.
              Generate it with <code className="rounded bg-slate-800 px-1 py-0.5 text-emerald-300">./lakehouse share start</code> for
              external access, or use the localhost version for local testing.
            </p>
            <CodeBlock
              title="delta-sharing-profile.json"
              language="json"
              code={`{
  "shareCredentialsVersion": 1,
  "endpoint": "https://localhost:8443/delta-sharing",
  "bearerToken": "<your-token>"
}`}
            />
          </div>

          {/* Recipient code examples */}
          <div className="card">
            <h2 className="mb-4 text-sm font-semibold text-white">
              Recipient Code Examples
            </h2>
            <div className="space-y-4">
              <CodeBlock
                title="Python + pandas"
                language="python"
                code={`# pip install delta-sharing
import delta_sharing

profile = "delta-sharing-profile.json"

# List all shared tables
client = delta_sharing.SharingClient(profile)
tables = client.list_all_tables()
print(tables)

# Read a shared table as Pandas DataFrame
table_url = profile + "#lakehouse_share.default.products_example"
df = delta_sharing.load_as_pandas(table_url)
print(df.head())`}
              />

              <CodeBlock
                title="PySpark"
                language="python"
                code={`profile = "delta-sharing-profile.json"
table_url = profile + "#lakehouse_share.default.products_example"

df = spark.read.format("deltaSharing").load(table_url)
df.show()`}
              />

              <CodeBlock
                title="Databricks SQL"
                language="sql"
                code={`-- 1. Upload the profile file to your Databricks workspace
-- 2. Create a catalog from the share:

CREATE CATALOG IF NOT EXISTS lakehouse_remote
USING SHARE \`provider_name\`.\`lakehouse_share\`;

-- 3. Query shared tables:
SELECT * FROM lakehouse_remote.default.products_example;`}
              />
            </div>
          </div>

          {/* Quick commands */}
          <div className="card">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
              <Terminal size={16} className="text-slate-400" />
              Quick Commands
            </h2>
            <div className="space-y-3">
              {[
                { label: "Start external sharing", cmd: "./lakehouse share start" },
                { label: "Stop sharing", cmd: "./lakehouse share stop" },
                { label: "Check sharing status", cmd: "./lakehouse share status" },
                {
                  label: "Add a table to the share",
                  cmd: "# Edit docker/delta-sharing/server.yaml, then:\ndocker compose up -d --no-deps --force-recreate delta-sharing",
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-start justify-between rounded-lg border border-slate-800 bg-surface-dark p-3"
                >
                  <div className="flex-1">
                    <p className="mb-1 text-xs text-slate-400">{item.label}</p>
                    <pre className="font-mono text-xs text-emerald-300 whitespace-pre-wrap">
                      {item.cmd}
                    </pre>
                  </div>
                  <CopyButton text={item.cmd} />
                </div>
              ))}
            </div>
          </div>

          <div className="text-center">
            <a
              href="https://delta.io/sharing/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-accent hover:text-accent-hover"
            >
              OpenSharing Documentation
              <ExternalLink size={14} />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
