// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest } from "next/server";
import { appendRun, type RunHistoryEntry } from "@/lib/s3";
import { requireEnv } from "@/lib/env";
import { codeExecutionEnabled, codeExecutionDisabledResponse } from "@/lib/features";

const JUPYTER_URL = () => process.env.JUPYTER_URL || "http://jupyter:8888";
const JUPYTER_TOKEN = () => requireEnv("JUPYTER_TOKEN");
const PIPELINES_DIR = process.env.PIPELINES_DIR!;

const DONE_MARKER = "__PIPELINE_DONE__";
const TIMEOUT_MS = 900_000;

let pipelineLock = false;
let pipelineLockTime = 0;

const EXIT_MESSAGES: Record<number, string> = {
  0: "Pipeline completed successfully.",
  1: "Pipeline failed. Check the output above for errors.",
  2: "Pipeline command had invalid arguments.",
  127: "spark-pipelines command not found. Ensure pyspark[pipelines] is installed.",
  126: "spark-pipelines command found but not executable.",
  137: "Pipeline was killed (out of memory or timeout).",
  143: "Pipeline was terminated by signal.",
};

const STEP_MARKER = "__STEP__";

function stripAnsi(str: string): string {
  return str
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "")
    .replace(/\x1b\][^\x07]*\x07/g, "")
    .replace(/\x1b\[\?[0-9;]*[a-zA-Z]/g, "")
    .replace(/\r/g, "");
}

function cleanLine(line: string): string | null {
  if (!line.trim()) return null;
  if (line.includes(DONE_MARKER)) return null;
  if (line.includes(STEP_MARKER)) return null;
  if (line.includes("jovyan@jupyter")) return null;
  if (line.match(/^\(base\)\s*$/)) return null;
  if (line.startsWith("cd ") || line.startsWith("export ")) return null;
  if (line.startsWith("echo ")) return null;
  if (line.startsWith("mkdir ")) return null;
  if (line.startsWith("printf ")) return null;
  if (PIPELINES_DIR) {
    line = line.replaceAll(PIPELINES_DIR + "/", "").replaceAll(PIPELINES_DIR, "");
  }
  return line;
}

// Only static configs that MUST be set at JVM startup go in spark-defaults.conf.
// Dynamic configs (S3A hadoop settings) belong in the pipeline spec's configuration section.
// Putting spark.hadoop.* here causes a hang in the Spark Connect launcher.
//
// IMPORTANT: keep these package versions on the stack-wide pins (CLAUDE.md /
// config/spark/spark-defaults.conf). Delta MUST be 4.3.1 — 4.3.0 NPEs through
// the UC connector (I-02) and resolves unitycatalog-client 0.5.0 instead of the
// required 0.5.1, so a dashboard-launched pipeline would diverge from the CLI.
const SDP_CONF_LINES = [
  "spark.jars.packages io.delta:delta-spark_4.1_2.13:4.3.1,org.apache.hadoop:hadoop-aws:3.4.1",
  "spark.sql.extensions io.delta.sql.DeltaSparkSessionExtension",
  "spark.sql.catalog.spark_catalog org.apache.spark.sql.delta.catalog.DeltaCatalog",
  "spark.sql.sources.default delta",
  "spark.sql.warehouse.dir s3a://lakehouse/warehouse",
];

export async function POST(req: NextRequest) {
  // D6 / T-3.8: running a pipeline shells out on the Jupyter terminal — disabled
  // unless code-execution is explicitly enabled.
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  // Auto-release stale locks after 20 minutes (safety valve)
  if (pipelineLock && Date.now() - pipelineLockTime > 20 * 60 * 1000) {
    pipelineLock = false;
  }
  if (pipelineLock) {
    return Response.json(
      { error: "A pipeline is already running. Wait for it to finish." },
      { status: 409 }
    );
  }
  pipelineLock = true;
  pipelineLockTime = Date.now();

  const startTime = Date.now();
  let spec = `${PIPELINES_DIR}/spark-pipeline.yml`;
  let mode: "run" | "dry-run" = "run";
  let fullRefresh = false;

  try {
    const body = await req.json().catch(() => ({}));
    const specFile = body.specPath || "spark-pipeline.yml";
    // Only a plain relative .yml/.yaml path inside PIPELINES_DIR: no traversal,
    // no absolute paths, no shell metacharacters — this value is interpolated
    // into a shell command below. Mirrors the /api/pipelines POST guard (T-3.7).
    if (
      specFile.startsWith("/") ||
      specFile.includes("..") ||
      !/^[A-Za-z0-9._/-]+\.ya?ml$/.test(specFile)
    ) {
      pipelineLock = false;
      return Response.json({ error: "Invalid spec path" }, { status: 400 });
    }
    spec = `${PIPELINES_DIR}/${specFile}`;
    mode = body.dryRun ? "dry-run" : "run";
    fullRefresh = body.fullRefresh === true;
  } catch {}

  const jupyterUrl = JUPYTER_URL();
  const token = JUPYTER_TOKEN();

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      function send(event: string, data: unknown) {
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      }

      let termName: string | null = null;

      try {
        send("step", { step: "connect", label: "Connecting to Jupyter..." });

        const termRes = await fetch(`${jupyterUrl}/api/terminals`, {
          method: "POST",
          headers: {
            Authorization: `token ${token}`,
            "Content-Type": "application/json",
          },
          signal: AbortSignal.timeout(10_000),
        }).catch(() => null);

        if (!termRes || !termRes.ok) {
          send("error", { message: "Cannot reach Jupyter. Is the container running?" });
          const entry = buildEntry(spec, mode, fullRefresh, 1, "Cannot reach Jupyter. Is the container running?", "", startTime);
          await saveQuietly(entry);
          controller.close();
          return;
        }

        const termData = await termRes.json();
        termName = termData.name;
        const wsProto = jupyterUrl.replace(/^http/, "ws");
        const wsUrl = `${wsProto}/terminals/websocket/${termName}?token=${token}`;

        await new Promise<void>((resolve) => {
          const ws = new WebSocket(wsUrl);
          let buf = "";
          let exitCode: number | null = null;
          let lastStepSent = "";

          const timer = setTimeout(() => {
            send("output", { text: "[Timed out after 15 minutes]" });
            send("done", { exitCode: null, message: "Pipeline timed out after 15 minutes." });
            try { ws.close(); } catch {}
            resolve();
          }, TIMEOUT_MS);

          ws.addEventListener("open", () => {
            const sdpConf = SDP_CONF_LINES.join("\\n");
            const refreshFlag = fullRefresh ? " --full-refresh-all" : "";
            const specFileName = spec.startsWith(PIPELINES_DIR)
              ? spec.slice(PIPELINES_DIR.length + 1)
              : spec;

            const s3Key = requireEnv("AWS_ACCESS_KEY_ID");
            const s3Secret = requireEnv("AWS_SECRET_ACCESS_KEY");

            const steps = [
              `export PATH="/opt/conda/bin:$PATH"`,
              `export AWS_ACCESS_KEY_ID="${s3Key}"`,
              `export AWS_SECRET_ACCESS_KEY="${s3Secret}"`,
              `pkill -9 -f spark-pipelines 2>/dev/null; pkill -9 -f SparkPipelines 2>/dev/null; pkill -9 -f pyspark-shell 2>/dev/null; sleep 2`,
              `cd ${PIPELINES_DIR}`,
            ];

            if (fullRefresh) {
              steps.push(
                `echo "${STEP_MARKER}:clean"`,
                `echo "Cleaning S3 table data for full refresh..."`,
                `python clean_tables.py`,
              );
            }

            const log4jLines = [
              "rootLogger.level = warn",
              "rootLogger.appenderRef.stdout.ref = console",
              "appender.console.type = Console",
              "appender.console.name = console",
              "appender.console.target = SYSTEM_ERR",
              "appender.console.layout.type = PatternLayout",
              "appender.console.layout.pattern = %%d{HH:mm:ss} %%p %%c{1}: %%m%%n",
              "logger.spark.name = org.apache.spark",
              "logger.spark.level = info",
              "logger.delta.name = io.delta",
              "logger.delta.level = info",
              "logger.catalyst.name = org.apache.spark.sql.catalyst",
              "logger.catalyst.level = warn",
              "logger.codegen.name = org.apache.spark.sql.catalyst.expressions.codegen",
              "logger.codegen.level = warn",
              "logger.netty.name = io.netty",
              "logger.netty.level = warn",
              "logger.artifact.name = org.apache.spark.sql.connect.artifact",
              "logger.artifact.level = warn",
            ].join("\\n");

            steps.push(
              `rm -rf /tmp/spark-* /tmp/sdp-conf 2>/dev/null`,
              `mkdir -p /tmp/sdp-conf`,
              `printf '${sdpConf}\\n' > /tmp/sdp-conf/spark-defaults.conf`,
              `printf '${log4jLines}\\n' > /tmp/sdp-conf/log4j2.properties`,
              `echo "${STEP_MARKER}:deps"`,
              `PYTHONUNBUFFERED=1 SPARK_CONF_DIR=/tmp/sdp-conf spark-pipelines ${mode} --spec '${specFileName}'${refreshFlag} 2>&1`,
              `RC=$?`,
            );

            if (mode === "run") {
              steps.push(
                `if [ $RC -eq 0 ]; then echo "${STEP_MARKER}:sync"; echo "Syncing tables to Unity Catalog..."; python sync_to_uc.py; RC=$?; fi`,
              );
            }

            steps.push(`echo "${DONE_MARKER}_$RC"`);

            ws.send(JSON.stringify(["stdin", steps.join("; ") + "\r"]));
          });

          ws.addEventListener("message", (event) => {
            const data = JSON.parse(String(event.data));
            if (data[0] !== "stdout") return;

            const chunk = data[1] as string;
            buf += chunk;

            const stripped = stripAnsi(chunk);
            for (const rawLine of stripped.split("\n")) {
              const trimmed = rawLine.trim();

              // Only match step markers that are the ENTIRE line (echo output),
              // not embedded in the command-line echo which contains all markers
              if (trimmed.match(new RegExp(`^${STEP_MARKER}:\\w+$`))) {
                const step = trimmed.split(":")[1];
                if (step !== lastStepSent) {
                  lastStepSent = step;
                  send("step", { step });
                }
                continue;
              }

              // Auto-detect Ivy dependency resolution
              if (trimmed.startsWith(":: resolving dependencies") || trimmed.startsWith(":: retrieving ::")) {
                if (lastStepSent !== "deps") {
                  lastStepSent = "deps";
                  send("step", { step: "deps" });
                }
              }

              // Auto-detect Spark session startup
              if (
                trimmed.includes("SparkUI") ||
                trimmed.includes("Setting default log level") ||
                trimmed.includes("SparkContext") ||
                trimmed.includes("SparkEnv") ||
                trimmed.includes("BlockManager")
              ) {
                if (lastStepSent !== "spark") {
                  lastStepSent = "spark";
                  send("step", { step: "spark" });
                }
              }

              // Auto-detect pipeline execution starting
              if (
                trimmed.includes("Running dataset") ||
                trimmed.includes("materialized_view") ||
                trimmed.includes("streaming_table") ||
                trimmed.includes("Analyzing") ||
                trimmed.includes("RUNNING") ||
                trimmed.includes("bronze_") ||
                trimmed.includes("silver_") ||
                trimmed.includes("gold_")
              ) {
                if (lastStepSent !== "pipeline") {
                  lastStepSent = "pipeline";
                  send("step", { step: "pipeline" });
                }
              }

              const cleaned = cleanLine(trimmed);
              if (cleaned) {
                send("output", { text: cleaned });
              }
            }

            const doneMatch = buf.match(new RegExp(`${DONE_MARKER}_(\\d+)`));
            if (doneMatch) {
              exitCode = parseInt(doneMatch[1], 10);
              clearTimeout(timer);

              const allOutput = stripAnsi(buf)
                .split("\n")
                .map(cleanLine)
                .filter(Boolean)
                .join("\n")
                .trim();

              const message = EXIT_MESSAGES[exitCode] ?? `Pipeline exited with code ${exitCode}.`;
              const displayMessage = fullRefresh && message ? `[Full Refresh] ${message}` : message;

              send("done", { exitCode, message: displayMessage, output: allOutput });

              const entry = buildEntry(spec, mode, fullRefresh, exitCode, message, allOutput || "(no output)", startTime);
              saveQuietly(entry);

              try { ws.close(); } catch {}
              resolve();
            }
          });

          ws.addEventListener("error", () => {
            clearTimeout(timer);
            send("error", { message: "WebSocket connection to Jupyter terminal failed" });
            resolve();
          });
        });

      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unexpected error";
        send("error", { message: msg });
      } finally {
        pipelineLock = false;
        if (termName) {
          await fetch(`${jupyterUrl}/api/terminals/${termName}`, {
            method: "DELETE",
            headers: { Authorization: `token ${token}` },
          }).catch(() => {});
        }
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

function buildEntry(
  spec: string,
  mode: "run" | "dry-run",
  fullRefresh: boolean,
  exitCode: number | null,
  message: string | null,
  output: string,
  startTime: number
): RunHistoryEntry {
  return {
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    spec,
    mode,
    exitCode,
    message: fullRefresh && message ? `[Full Refresh] ${message}` : message,
    output,
    durationMs: Date.now() - startTime,
  };
}

async function saveQuietly(entry: RunHistoryEntry) {
  try {
    await appendRun(entry);
  } catch (err) {
    console.error("Failed to save run history to the object store:", err);
  }
}
