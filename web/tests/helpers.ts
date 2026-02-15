/**
 * Integration test helpers for FiestaBoard.
 *
 * Provides utilities to interact with the mock Vestaboard API
 * and reset state between tests.
 */
import { test as base, expect } from "@playwright/test";

/** Extend Playwright's base test with per-test backend state cleanup. */
export const test = base.extend<{ resetBackend: void }>({
  // eslint-disable-next-line no-empty-pattern
  resetBackend: [async ({}, use) => {
    // Reset mock board state before the test
    await fetch("http://localhost:7000/mock/reset", { method: "POST" });

    // Wipe persisted data so the backend behaves as first-run
    await fetch("http://localhost:8000/debug/reset-config", {
      method: "POST",
    }).catch(() => {
      // Endpoint may not exist — not critical
    });

    await use();
  }, { auto: true }],
});

export { expect };

/** Read the mock board's internal state (message history, etc.). */
export async function getMockBoardState() {
  const res = await fetch("http://localhost:7000/mock/state");
  return res.json();
}

/** Wait until the API server is ready. */
export async function waitForApi(timeoutMs = 15_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch("http://localhost:8000/health");
      if (res.ok) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("API server did not become ready");
}
