/**
 * Vitest test setup for frontend tests.
 *
 * Provides global mocks for Next.js server-side APIs and fetch
 * so tests can run without a real Next.js server or Docker services.
 */

import { vi } from "vitest";

// Default the code-execution feature flag ON for tests so the gated routes reach
// their real logic (path-traversal, validation). The dedicated feature-flag test
// (feature_flags.test.ts) toggles it OFF per-case to assert the disabled path.
process.env.DASHBOARD_ALLOW_CODE_EXECUTION = "true";

// Mock global fetch for all tests
global.fetch = vi.fn();

// Mock AbortSignal.timeout (not available in all Node.js versions)
if (!AbortSignal.timeout) {
  (AbortSignal as unknown as Record<string, unknown>).timeout = (ms: number) => {
    const controller = new AbortController();
    setTimeout(() => controller.abort(), ms);
    return controller.signal;
  };
}
