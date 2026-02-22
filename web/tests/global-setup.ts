/**
 * Playwright global setup.
 *
 * Runs once before all tests to ensure a clean environment:
 *  - Removes the backend data/config.json so the API starts in first-run mode
 *  - Resets the mock board state
 *  - Auto-detects Docker networking and sets MOCK_BOARD_HOST
 */
import { rm } from "fs/promises";
import path from "path";

const API_URL = `http://localhost:${process.env.API_PORT || "8000"}`;

async function globalSetup() {
  // Remove backend config so the API reports is_first_run = true
  const configPath = path.resolve(__dirname, "../../data/config.json");
  try {
    await rm(configPath, { force: true });
  } catch {
    // File may not exist — that's fine
  }

  // Also clean any leftover settings / pages data
  const dataDir = path.resolve(__dirname, "../../data");
  for (const file of ["settings.json", "pages.json", "schedules.json"]) {
    try {
      await rm(path.join(dataDir, file), { force: true });
    } catch {
      // ignore
    }
  }

  // Auto-detect Docker: if the API can reach the mock board via Docker
  // service name, use that; otherwise fall back to localhost.
  if (!process.env.MOCK_BOARD_HOST) {
    try {
      const res = await fetch(`${API_URL}/config/board/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_mode: "local",
          local_api_key: "test-key",
          host: "fiestaboard-mock-board",
        }),
      });
      const data = await res.json();
      if (data.success) {
        process.env.MOCK_BOARD_HOST = "fiestaboard-mock-board";
      }
    } catch {
      // API not reachable yet or not running in Docker — use default
    }
  }
}

export default globalSetup;
