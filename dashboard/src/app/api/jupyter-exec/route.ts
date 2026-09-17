// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { requireEnv } from "@/lib/env";
import { codeExecutionEnabled, codeExecutionDisabledResponse } from "@/lib/features";
import { cappedTimeout } from "@/lib/exec";

/**
 * SECURITY NOTE: This endpoint allows arbitrary Python code execution on the
 * Jupyter kernel. In the default single-user local setup, this is expected
 * behavior. For multi-user or network-exposed deployments:
 * - Add authentication (require a session token or API key)
 * - Add rate limiting (max N requests per minute per client)
 * - Add audit logging (log code snippets, timestamps, client IPs)
 * - Consider sandboxing the execution environment
 */

const JUPYTER_URL = () => process.env.JUPYTER_URL || "http://jupyter:8888";
const JUPYTER_TOKEN = () => requireEnv("JUPYTER_TOKEN");

function wsUrl(): string {
  return JUPYTER_URL().replace(/^http/, "ws");
}

interface KernelOutput {
  output_type: string;
  text?: string[];
  data?: Record<string, unknown>;
  name?: string;
  ename?: string;
  evalue?: string;
  traceback?: string[];
  execution_count?: number;
}

function executeViaWebSocket(
  kernelId: string,
  code: string,
  timeoutMs = 0
): Promise<{ status: string; outputs: KernelOutput[]; execution_count?: number }> {
  return new Promise((resolve, reject) => {
    const url = `${wsUrl()}/api/kernels/${kernelId}/channels?token=${JUPYTER_TOKEN()}`;
    const ws = new WebSocket(url);
    const outputs: KernelOutput[] = [];
    const msgId = crypto.randomUUID();
    const sessionId = crypto.randomUUID();
    let execCount: number | undefined;

    // Always a finite timer — the cap is enforced here regardless of the caller.
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error("Execution timed out"));
    }, cappedTimeout(timeoutMs));

    ws.addEventListener("open", () => {
      ws.send(
        JSON.stringify({
          header: {
            msg_id: msgId,
            msg_type: "execute_request",
            username: "frontend",
            session: sessionId,
            date: new Date().toISOString(),
            version: "5.3",
          },
          parent_header: {},
          metadata: {},
          content: {
            code,
            silent: false,
            store_history: true,
            user_expressions: {},
            allow_stdin: false,
            stop_on_error: true,
          },
          channel: "shell",
        })
      );
    });

    ws.addEventListener("message", (event) => {
      let msg: {
        header: { msg_type: string };
        parent_header?: { msg_id?: string };
        content: Record<string, unknown>;
        channel?: string;
        msg_type?: string;
      };
      try {
        msg = JSON.parse(String(event.data));
      } catch {
        return;
      }

      if (msg.parent_header?.msg_id !== msgId) return;

      const msgType = msg.msg_type ?? msg.header?.msg_type;
      const channel = msg.channel;

      if (channel === "iopub" || !channel) {
        switch (msgType) {
          case "stream":
            outputs.push({
              output_type: "stream",
              name: msg.content.name as string,
              text: [msg.content.text as string],
            });
            break;
          case "execute_result":
            execCount = msg.content.execution_count as number;
            outputs.push({
              output_type: "execute_result",
              data: msg.content.data as Record<string, unknown>,
              execution_count: execCount,
            });
            break;
          case "display_data":
            outputs.push({
              output_type: "display_data",
              data: msg.content.data as Record<string, unknown>,
            });
            break;
          case "error":
            outputs.push({
              output_type: "error",
              ename: msg.content.ename as string,
              evalue: msg.content.evalue as string,
              traceback: msg.content.traceback as string[],
            });
            break;
        }
      }

      if (
        (channel === "shell" || !channel) &&
        msgType === "execute_reply"
      ) {
        execCount = msg.content.execution_count as number;
        if (timer) clearTimeout(timer);
        ws.close();
        resolve({
          status: msg.content.status as string,
          outputs,
          execution_count: execCount,
        });
      }
    });

    ws.addEventListener("error", () => {
      if (timer) clearTimeout(timer);
      reject(new Error("WebSocket connection to Jupyter kernel failed"));
    });

    ws.addEventListener("close", (event) => {
      if (timer) clearTimeout(timer);
      // If the socket closes without an execute_reply (e.g. kernel restart
      // mid-exec), still settle the promise so the awaiting handler can't hang.
      // resolve/reject after a prior settle is a no-op.
      if (outputs.length > 0) {
        resolve({ status: "ok", outputs, execution_count: execCount });
      } else if (!event.wasClean) {
        reject(new Error("WebSocket closed unexpectedly"));
      } else {
        reject(new Error("Kernel closed the connection before completing"));
      }
    });
  });
}

export async function POST(req: NextRequest) {
  // D6 / T-3.8: arbitrary-code execution is disabled unless explicitly enabled.
  if (!codeExecutionEnabled()) return codeExecutionDisabledResponse();
  try {
    const body = await req.json();
    const { kernelId, code, timeoutMs } = body as {
      kernelId: string;
      code: string;
      timeoutMs?: number;
    };

    if (!kernelId || !code) {
      return NextResponse.json(
        { error: "kernelId and code are required" },
        { status: 400 }
      );
    }

    // The finite cap is enforced inside executeViaWebSocket (cappedTimeout), so a
    // missing or 0/negative client timeout still hits the 120s ceiling.
    const result = await executeViaWebSocket(kernelId, code, timeoutMs ?? 0);
    return NextResponse.json(result);
  } catch (e) {
    const message = e instanceof Error ? e.message : "Execution failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
