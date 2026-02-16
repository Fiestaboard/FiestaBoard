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

    await use();
  }, { auto: true }],
});

export { expect };

/** Read the mock board's internal state (message history, etc.). */
export async function getMockBoardState() {
  const res = await fetch("http://localhost:7000/mock/state");
  return res.json();
}

/**
 * Configure the board via the API so the app is no longer in first-run mode.
 * Call this in tests that need a working backend without running the wizard.
 */
export async function configureBoard() {
  await fetch("http://localhost:8000/config/board", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_mode: "local",
      local_api_key: "test-key",
      host: "localhost",
    }),
  });
}

/**
 * Clear the board configuration so the backend returns to first-run mode.
 * Use this before tests that need the setup wizard to appear.
 */
export async function clearBoardConfig() {
  await fetch("http://localhost:8000/config/board", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_mode: "local",
      local_api_key: "",
      host: "",
    }),
  });
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
