/**
 * Playwright global setup.
 *
 * Runs once before all tests to ensure a clean environment:
 *  - Removes the backend data/config.json so the API starts in first-run mode
 *  - Resets the mock board state
 */
import { rm } from "fs/promises";
import path from "path";

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
}

export default globalSetup;
