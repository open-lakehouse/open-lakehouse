// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

"use client";

import {
  HardDrive,
  FolderOpen,
  FileText,
} from "lucide-react";

const buckets = [
  {
    name: "lakehouse",
    prefixes: ["warehouse/", "catalog/", "mlflow/", "sharing/", "tmp/"],
    description: "Primary lakehouse storage bucket",
  },
];

export default function StoragePage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Storage</h1>
          <p className="mt-1 text-sm text-slate-400">
            SeaweedFS S3-compatible object storage
          </p>
        </div>
      </div>

      {/* Bucket overview */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white">Buckets</h2>
        {buckets.map((bucket) => (
          <div key={bucket.name} className="card space-y-4">
            <div className="flex items-center gap-3">
              <HardDrive size={20} className="text-accent" />
              <div>
                <h3 className="text-sm font-semibold text-white">
                  {bucket.name}
                </h3>
                <p className="text-xs text-slate-400">{bucket.description}</p>
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              {bucket.prefixes.map((prefix) => (
                <div
                  key={prefix}
                  className="flex items-center gap-3 rounded-lg border border-slate-800 bg-surface-dark px-4 py-3"
                >
                  {prefix.endsWith("/") ? (
                    <FolderOpen size={16} className="text-amber-400" />
                  ) : (
                    <FileText size={16} className="text-slate-400" />
                  )}
                  <div>
                    <p className="font-mono text-sm text-slate-300">
                      {prefix}
                    </p>
                    <p className="text-[11px] text-slate-500">
                      s3://{bucket.name}/{prefix}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      {/* S3 connection info */}
      <section className="card">
        <h2 className="mb-4 text-sm font-semibold text-white">
          S3 Connection Details
        </h2>
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          {[
            { label: "Endpoint", value: "http://localhost:8333" },
            { label: "Region", value: "us-east-1" },
            { label: "Path style", value: "true" },
            {
              label: "Internal endpoint",
              value: "http://seaweedfs:8333 (docker network)",
            },
          ].map((item) => (
            <div key={item.label}>
              <span className="text-xs text-slate-500">{item.label}</span>
              <p className="mt-0.5 font-mono text-xs text-slate-300">
                {item.value}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
