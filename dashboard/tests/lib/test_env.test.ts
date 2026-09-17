/**
 * Tests for the requireEnv utility function.
 */

import { describe, it, expect, afterEach } from "vitest";

describe("requireEnv", () => {
  const originalEnv = { ...process.env };

  afterEach(() => {
    process.env = { ...originalEnv };
  });

  it("returns the value when env var is set", async () => {
    process.env.TEST_VAR = "test_value";
    const { requireEnv } = await import("@/lib/env");
    expect(requireEnv("TEST_VAR")).toBe("test_value");
  });

  it("throws when env var is missing", async () => {
    delete process.env.TEST_VAR;
    const { requireEnv } = await import("@/lib/env");
    expect(() => requireEnv("TEST_VAR")).toThrow(
      "Missing required environment variable: TEST_VAR"
    );
  });

  it("throws when env var is empty string", async () => {
    process.env.TEST_VAR = "";
    const { requireEnv } = await import("@/lib/env");
    expect(() => requireEnv("TEST_VAR")).toThrow(
      "Missing required environment variable: TEST_VAR"
    );
  });
});
