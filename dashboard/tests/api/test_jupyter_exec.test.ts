/**
 * Tests for the jupyter-exec server-side timeout cap (cappedTimeout).
 * A client-supplied timeout may only lower the cap, never remove or exceed it.
 */

import { describe, it, expect } from "vitest";
import { cappedTimeout } from "@/lib/exec";

describe("jupyter-exec cappedTimeout", () => {
  it("clamps 0 / negative / absent to the 120s cap", () => {
    expect(cappedTimeout(0)).toBe(120_000);
    expect(cappedTimeout(-5)).toBe(120_000);
    expect(cappedTimeout(NaN)).toBe(120_000);
  });

  it("clamps a value above the cap down to 120s", () => {
    expect(cappedTimeout(999_999_999)).toBe(120_000);
  });

  it("allows a smaller client timeout", () => {
    expect(cappedTimeout(5_000)).toBe(5_000);
  });
});
