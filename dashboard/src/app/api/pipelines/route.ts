// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { readFileSync, readdirSync, writeFileSync, mkdirSync, existsSync, statSync } from "fs";
import { join, relative, resolve, sep } from "path";
import { codeExecutionEnabled, codeExecutionDisabledResponse } from "@/lib/features";

const PIPELINES_DIR = "/app/pipelines";

// True iff a candidate relative path resolves to PIPELINES_DIR itself or a path
// nested inside it (T-3.7). The trailing-separator boundary is what rejects a
// sibling directory such as /app/pipelines-evil that a bare
// startsWith(resolve(PIPELINES_DIR)) would wrongly admit.
function isInsidePipelinesDir(candidate: string): boolean {
  const base = resolve(PIPELINES_DIR);
  const resolved = resolve(base, candidate);
  return resolved === base || resolved.startsWith(base + sep);
}

function walkDir(dir: string): string[] {
  const files: string[] = [];
  if (!existsSync(dir)) return files;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkDir(full));
    } else {
      files.push(relative(PIPELINES_DIR, full));
    }
  }
  return files;
}

export async function GET() {
  // D6 / T-3.8: the entire pipelines feature (not just writes) is off unless
  // code-execution is enabled — the disabled surface must not respond at all.
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  try {
    if (!existsSync(PIPELINES_DIR)) {
      return NextResponse.json({ specs: [], transformations: [] });
    }

    const allFiles = walkDir(PIPELINES_DIR);
    const specs = allFiles.filter((f) => f.endsWith(".yml") || f.endsWith(".yaml"));
    const transformations = allFiles.filter((f) => f.endsWith(".py") || f.endsWith(".sql"));

    const specContents = specs.map((f) => {
      const full = join(PIPELINES_DIR, f);
      return {
        path: f,
        content: readFileSync(full, "utf-8"),
        modified: statSync(full).mtime.toISOString(),
      };
    });

    const transformationContents = transformations.map((f) => {
      const full = join(PIPELINES_DIR, f);
      return {
        path: f,
        content: readFileSync(full, "utf-8"),
        modified: statSync(full).mtime.toISOString(),
      };
    });

    return NextResponse.json({
      specs: specContents,
      transformations: transformationContents,
    });
  } catch {
    return NextResponse.json({ error: "Failed to read pipelines" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  // D6 / T-3.8: writing pipeline files is a mutation — disabled unless enabled.
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  try {
    const { specName, specContent, transformations } = await req.json();

    if (!specName || !specContent) {
      return NextResponse.json({ error: "specName and specContent required" }, { status: 400 });
    }

    const specFileName = specName.endsWith(".yml") ? specName : `${specName}.yml`;

    // Prevent path traversal (T-3.7).
    if (!isInsidePipelinesDir(specFileName)) {
      return NextResponse.json({ error: "Invalid path" }, { status: 400 });
    }

    const specPath = join(PIPELINES_DIR, specFileName);
    writeFileSync(specPath, specContent, "utf-8");

    if (transformations && Array.isArray(transformations)) {
      for (const t of transformations) {
        if (!t.path || !t.content) continue;
        // Prevent path traversal (T-3.7).
        if (!isInsidePipelinesDir(t.path)) {
          return NextResponse.json({ error: "Invalid path" }, { status: 400 });
        }
        const tPath = join(PIPELINES_DIR, t.path);
        const tDir = join(tPath, "..");
        if (!existsSync(tDir)) mkdirSync(tDir, { recursive: true });
        writeFileSync(tPath, t.content, "utf-8");
      }
    }

    return NextResponse.json({ ok: true, specPath: relative(PIPELINES_DIR, specPath) });
  } catch {
    return NextResponse.json({ error: "Failed to create pipeline" }, { status: 500 });
  }
}
