/**
 * Tests for the pipelines API route (/api/pipelines).
 *
 * Validates path traversal prevention, input validation, and basic operation.
 * These tests mock the filesystem so they run without Docker.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

// Mock the fs module before importing the route
vi.mock("fs", () => ({
  readFileSync: vi.fn().mockReturnValue("name: test\n"),
  readdirSync: vi.fn().mockReturnValue([]),
  writeFileSync: vi.fn(),
  mkdirSync: vi.fn(),
  existsSync: vi.fn().mockReturnValue(true),
  statSync: vi.fn().mockReturnValue({ mtime: new Date() }),
}));

// Import after mocks
import { GET, POST } from "@/app/api/pipelines/route";
import { writeFileSync } from "fs";

describe("GET /api/pipelines", () => {
  it("returns specs and transformations arrays", async () => {
    const response = await GET();
    const data = await response.json();

    expect(data).toHaveProperty("specs");
    expect(data).toHaveProperty("transformations");
    expect(Array.isArray(data.specs)).toBe(true);
    expect(Array.isArray(data.transformations)).toBe(true);
  });
});

describe("POST /api/pipelines", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 when specName is missing", async () => {
    const req = new NextRequest("http://localhost:3000/api/pipelines", {
      method: "POST",
      body: JSON.stringify({ specContent: "name: test\n" }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(req);
    expect(response.status).toBe(400);

    const data = await response.json();
    expect(data.error).toContain("required");
  });

  it("returns 400 when specContent is missing", async () => {
    const req = new NextRequest("http://localhost:3000/api/pipelines", {
      method: "POST",
      body: JSON.stringify({ specName: "test-pipeline" }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(req);
    expect(response.status).toBe(400);
  });

  it("creates a pipeline with valid input", async () => {
    const req = new NextRequest("http://localhost:3000/api/pipelines", {
      method: "POST",
      body: JSON.stringify({
        specName: "test-pipeline",
        specContent: "name: test_pipeline\nlibraries:\n  - glob:\n      include: transformations/**\n",
      }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(req);
    const data = await response.json();

    expect(response.status).toBe(200);
    expect(data.ok).toBe(true);
    expect(data.specPath).toContain("test-pipeline");
  });

  it("appends .yml extension when missing", async () => {
    const req = new NextRequest("http://localhost:3000/api/pipelines", {
      method: "POST",
      body: JSON.stringify({
        specName: "my-pipeline",
        specContent: "name: my_pipeline\n",
      }),
      headers: { "Content-Type": "application/json" },
    });

    await POST(req);

    // Check writeFileSync was called with .yml extension
    expect(writeFileSync).toHaveBeenCalledWith(
      expect.stringMatching(/my-pipeline\.yml$/),
      expect.any(String),
      "utf-8"
    );
  });

  it("rejects path traversal in specName with 400 (T-3.7)", async () => {
    // Inverts CP's original assertion: `../../../etc/passwd` resolves outside
    // PIPELINES_DIR and MUST be rejected, and nothing may be written.
    const req = new NextRequest("http://localhost:3000/api/pipelines", {
      method: "POST",
      body: JSON.stringify({
        specName: "../../../etc/passwd",
        specContent: "malicious content",
      }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(req);
    expect(response.status).toBe(400);

    const data = await response.json();
    expect(data.error).toBe("Invalid path");
    expect(writeFileSync).not.toHaveBeenCalled();
  });

  it("rejects a sibling-directory escape like /app/pipelines-evil (T-3.7)", async () => {
    // The trailing-separator boundary is what closes this hole: a bare
    // startsWith(resolve(PIPELINES_DIR)) would have admitted /app/pipelines-evil.
    const req = new NextRequest("http://localhost:3000/api/pipelines", {
      method: "POST",
      body: JSON.stringify({
        specName: "../pipelines-evil/x",
        specContent: "escape",
      }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(req);
    expect(response.status).toBe(400);
    expect(writeFileSync).not.toHaveBeenCalled();
  });

  it("rejects path traversal in transformation paths with 400 (T-3.7)", async () => {
    const req = new NextRequest("http://localhost:3000/api/pipelines", {
      method: "POST",
      body: JSON.stringify({
        specName: "safe-pipeline",
        specContent: "name: test\n",
        transformations: [
          { path: "../../etc/cron.d/evil", content: "* * * * * rm -rf /" },
        ],
      }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(req);
    expect(response.status).toBe(400);

    const data = await response.json();
    expect(data.error).toBe("Invalid path");
  });

  it("handles transformations with missing fields gracefully", async () => {
    const req = new NextRequest("http://localhost:3000/api/pipelines", {
      method: "POST",
      body: JSON.stringify({
        specName: "test-pipeline",
        specContent: "name: test\n",
        transformations: [
          { path: null, content: null },
          { path: "", content: "" },
          {},
        ],
      }),
      headers: { "Content-Type": "application/json" },
    });

    const response = await POST(req);
    // Should not crash
    expect(response.status).toBeLessThan(500);
  });
});
